import os
import time
import subprocess
import shutil
from datetime import datetime
from database import SessionLocal
from models import Build, Recipe, RecipeAsset
from celery_app import celery_app
from core.workspace import prepare_workspace, populate_extra_tree
from core.mkosi_config import generate_mkosi_conf
from core.packages import is_armbian


@celery_app.task(name="tasks.build_image.build_image_task", bind=True)
def build_image_task(self, build_id: str, recipe_id: int):
    from tasks import log_to_task

    db = SessionLocal()
    start_time = time.time()
    try:
        build = db.query(Build).filter(Build.id == build_id).first()
        recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
        assets = db.query(RecipeAsset).filter(RecipeAsset.recipe_id == recipe_id).all()

        if not build or not recipe:
            log_to_task(build_id, "[ERROR] Invalid build or recipe reference.", status="FAILED")
            return

        log_to_task(build_id, f"Starting OS image build for recipe '{recipe.name}' ({recipe.distribution} {recipe.release} - {recipe.architecture})...", status="RUNNING")

        # 1. Prepare Workspace & Extra Tree
        log_to_task(build_id, "[STEP 1/4] Preparing workspace directory and overlay filesystem...")
        ws_path = prepare_workspace(recipe.id, recipe)

        # Verify every package exists for the target architecture before mkosi
        # starts. Without this apt kills the build ten minutes in, and the log
        # gives no hint which package has no arm64 build. It runs before the
        # overlay tree is populated because it also decides which repositories
        # are worth writing into the image's sources.list.d.
        from core.arch_check import check_recipe_packages, has_critical

        exclude = frozenset()
        log_to_task(build_id, f"Verifying package availability for {recipe.architecture}...")
        check = check_recipe_packages(recipe, log=lambda m: log_to_task(build_id, m))

        if check.missing:
            build.missing_packages = list(check.missing)
            db.commit()

            summary = ", ".join(f"{m['name']} ({m['source']})" for m in check.missing)
            critical = [m["name"] for m in check.missing if m["reason"] == "critical"]

            if has_critical(check):
                raise RuntimeError(
                    f"Packages required for a bootable image are not available for "
                    f"{recipe.architecture}: {', '.join(critical)}. These are never skipped."
                )
            if not recipe.ignore_missing_arch_packages:
                raise RuntimeError(
                    f"{len(check.missing)} package(s) not available for {recipe.architecture}: {summary}. "
                    f"Enable 'skip packages missing for this architecture' in the recipe to build anyway."
                )

            exclude = frozenset(m["name"] for m in check.missing)
            log_to_task(build_id, f"[ARCH CHECK] Skipping {len(check.missing)} package(s) unavailable for {recipe.architecture}:")
            for m in check.missing:
                log_to_task(build_id, f"[ARCH CHECK]   - {m['name']} ({m['source']})")

        skip_repo_urls = frozenset(check.absent_repos)
        for url in check.absent_repos:
            log_to_task(build_id, f"[ARCH CHECK] Leaving {url} out of the image's APT sources -- it publishes nothing for {recipe.architecture}.")

        populate_extra_tree(recipe, assets, ws_path, skip_repo_urls=skip_repo_urls)

        # Pre-download all Edge platform packages into mkosi.extra/opt/edge_packages/
        try:
            from core.repo_downloader import download_edge_packages
            dl_files = download_edge_packages(recipe, ws_path, exclude=exclude)
            log_to_task(build_id, f"[REPO DOWNLOADER] Pre-downloaded {len(dl_files)} Edge platform .deb packages directly.")
        except Exception as e:
            log_to_task(build_id, f"[REPO DOWNLOADER WARNING] Failed to pre-download Edge packages: {e}")

        # 2. Generate mkosi.conf
        log_to_task(build_id, "[STEP 2/4] Generating mkosi.conf recipe configuration...")
        generate_mkosi_conf(recipe, ws_path, exclude=exclude, skip_repo_urls=skip_repo_urls)

        # 3. Execute mkosi build process
        log_to_task(build_id, "[STEP 3/4] Invoking mkosi systemd-nspawn build engine...")

        # Clean existing output directory if present
        shutil.rmtree(os.path.join(ws_path, "output"), ignore_errors=True)

        mkosi_bin = shutil.which("mkosi")
        if not mkosi_bin:
            log_to_task(build_id, "[WARNING] 'mkosi' binary not found in worker container PATH. Running in simulated build mode...")
            cmd = ["echo", "[SIMULATION] Built OS image successfully."]
        else:
            cmd = ["nice", "-n", "19", "ionice", "-c", "3", "mkosi", "--directory", ws_path, "--force", "build"]

        log_to_task(build_id, f"[EXEC] {' '.join(cmd)}")

        proc_env = os.environ.copy()
        proc_env["PYTHONUNBUFFERED"] = "1"
        proc_env["PYTHONIOENCODING"] = "utf-8"
        proc_env["TERM"] = "xterm-256color"

        import pty
        import re

        ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        master_fd, slave_fd = pty.openpty()

        try:
            process = subprocess.Popen(
                cmd,
                stdout=slave_fd,
                stderr=slave_fd,
                cwd=ws_path,
                env=proc_env,
                close_fds=True
            )
        finally:
            os.close(slave_fd)

        master_file = os.fdopen(master_fd, 'rb', buffering=0)
        last_progress_pct = -1
        last_cancel_check = 0.0
        line_buffer = b""

        from core import apt_diagnostics
        from core.log_throttle import RepeatCollapser

        # apt's complaints are kept aside: in the full log they drown among
        # thousands of lines, and they only matter if mkosi actually failed.
        apt_diag_lines = []
        # A stuck apt repeats one line indefinitely -- 39888 copies of the same
        # warning in one observed run. Every line is written to Postgres, so
        # runs of identical lines are collapsed before they get there.
        collapser = RepeatCollapser()

        while True:
            try:
                chunk = master_file.read(1024)
                if not chunk:
                    break
                line_buffer += chunk

                while b"\n" in line_buffer or b"\r" in line_buffer:
                    pos_n = line_buffer.find(b"\n")
                    pos_r = line_buffer.find(b"\r")
                    if pos_n != -1 and (pos_r == -1 or pos_n < pos_r):
                        pos = pos_n
                    else:
                        pos = pos_r

                    raw_line = line_buffer[:pos]
                    line_buffer = line_buffer[pos + 1:]

                    clean_line = raw_line.decode('utf-8', errors='replace')
                    clean_line = ANSI_ESCAPE.sub('', clean_line).strip()
                    if not clean_line:
                        continue

                    if "edge-base" in clean_line:
                        eb_match = re.search(r'edge-base(?:[:\w\-]+)?\s*\(?([0-9a-zA-Z\.\+\~\-]+)\)?', clean_line)
                        if eb_match:
                            v_str = eb_match.group(1).strip()
                            if len(v_str) >= 3 and v_str[0].isdigit():
                                try:
                                    with open(os.path.join(ws_path, "edge_base_version.txt"), "w") as f:
                                        f.write(v_str)
                                except Exception:
                                    pass

                    pct_match = re.search(r'(\d+)%', clean_line)
                    if pct_match:
                        pct = int(pct_match.group(1))
                        if pct % 5 == 0 and pct != last_progress_pct:
                            last_progress_pct = pct
                            log_to_task(build_id, clean_line)
                        continue

                    for out_line in collapser.feed(clean_line):
                        log_to_task(build_id, out_line)

                    if len(apt_diag_lines) < 200 and apt_diagnostics.is_diagnostic_line(clean_line):
                        apt_diag_lines.append(clean_line)

                    # Check if build was cancelled via API (throttled to once every 3s)
                    now = time.time()
                    if now - last_cancel_check > 3.0:
                        last_cancel_check = now
                        try:
                            db.refresh(build)
                            if build.status == "CANCELLED":
                                log_to_task(build_id, "[SYSTEM] Process termination requested by user. Terminating mkosi...")
                                process.terminate()
                                process.wait(timeout=5)
                                for out_line in collapser.flush():
                                    log_to_task(build_id, out_line)
                                master_file.close()
                                return
                        except Exception:
                            pass

            except Exception:
                break

        # Flush any remaining data in the line buffer
        if line_buffer:
            remaining = line_buffer.decode('utf-8', errors='replace')
            remaining = ANSI_ESCAPE.sub('', remaining).strip()
            if remaining:
                for rem_line in remaining.split('\n'):
                    rem_line = rem_line.strip()
                    if rem_line:
                        for out_line in collapser.feed(rem_line):
                            log_to_task(build_id, out_line)

        # Close the last run of repeated lines so its count reaches the log.
        for out_line in collapser.flush():
            log_to_task(build_id, out_line)

        master_file.close()

        return_code = process.wait()
        if return_code != 0 and mkosi_bin:
            dependency_misses = apt_diagnostics.parse_diagnostics(apt_diag_lines)
            if dependency_misses:
                log_to_task(build_id, "[ARCH CHECK] apt could not resolve some packages. The pre-flight check only")
                log_to_task(build_id, f"[ARCH CHECK] verifies top-level names, so a dependency is likely unavailable for {recipe.architecture}:")
                for m in dependency_misses:
                    log_to_task(build_id, f"[ARCH CHECK]   - {m['name']}: {m['detail']}")
                known = {m["name"] for m in (build.missing_packages or [])}
                build.missing_packages = list(build.missing_packages or []) + [
                    m for m in dependency_misses if m["name"] not in known
                ]
                db.commit()
            log_to_task(build_id, f"[ERROR] mkosi exited with return code {return_code}")
            raise subprocess.CalledProcessError(return_code, cmd)

        # 4. Finalize Artifact
        log_to_task(build_id, "[STEP 4/4] Finalizing build output artifacts...")

        outputs_dir = os.path.join(os.getenv("DURO_WORKSPACE_PATH", "/opt/data/duro_workspace"), "outputs")
        os.makedirs(outputs_dir, exist_ok=True)

        src_output = os.path.join(ws_path, "output")
        target_raw_file = None

        if os.path.exists(src_output) and os.listdir(src_output):
            all_files = [os.path.join(src_output, f) for f in os.listdir(src_output)]
            disk_files = [f for f in all_files if f.endswith(".raw") or f.endswith(".img") or f.endswith(".raw.xz")]
            if not disk_files:
                disk_files = [f for f in all_files if not f.endswith(".efi") and not f.endswith(".vmlinuz") and not f.endswith(".initrd")]
            if not disk_files:
                disk_files = all_files

            disk_files.sort(key=lambda f: os.path.getsize(f), reverse=True)
            target_raw_file = disk_files[0]

        # Загрузчик пишется до сжатия: BootROM RK3588 читает его с фиксированных
        # смещений в начале носителя, и без этого шага .raw.xz разворачивается в
        # незагружаемую карту -- а значит и firstboot, прошивающий SPI, никогда
        # не стартует.
        if is_armbian(recipe.distribution) and target_raw_file and target_raw_file.endswith(".raw"):
            from core.rk3588 import write_bootloader_into_image
            if not write_bootloader_into_image(target_raw_file, lambda m: log_to_task(build_id, m)):
                raise RuntimeError(
                    "Не удалось записать загрузчик RK3588 в образ -- плата с него не загрузится."
                )

        # Extract edge-base version for unified RAW.XZ naming scheme
        edge_base_ver = None
        try:
            from tasks.generate_iso import extract_edge_base_version
            edge_base_ver = extract_edge_base_version(ws_path, target_raw_file)
        except Exception:
            pass

        arch = (recipe.architecture if recipe and recipe.architecture else "amd64").lower()
        rel = (recipe.release if recipe and recipe.release else "bookworm").lower()
        ts_suffix = datetime.utcnow().strftime('%y%m%d-%H%M')

        # Dev builds are named edge-dev_* so they can never be mistaken for a
        # release artifact once both are sitting in the same outputs directory.
        prefix = "edge-dev" if (recipe and recipe.is_dev) else "edge"

        if edge_base_ver:
            raw_xz_filename = f"{prefix}_{edge_base_ver}_{arch}-{rel}_{ts_suffix}.raw.xz"
        else:
            raw_xz_filename = f"{prefix}_{arch}-{rel}_{ts_suffix}.raw.xz"

        final_raw_xz_path = os.path.join(outputs_dir, raw_xz_filename)

        if target_raw_file:
            if not target_raw_file.endswith(".xz"):
                total_bytes = os.path.getsize(target_raw_file)
                # DEBUG: use 85% of CPUs while tuning; revert to conc-quota formula later
                cpu_threads = max(1, int((os.cpu_count() or 2) * 0.85))
                log_to_task(build_id, f"Compressing raw disk image '{os.path.basename(target_raw_file)}' ({total_bytes} bytes) into {raw_xz_filename} using {cpu_threads} CPU threads...")
                try:
                    import threading
                    pass

                    xz_proc = subprocess.Popen(
                        ["nice", "-n", "19", "ionice", "-c", "3",
                         "xz", "-c", "-3", f"-T{cpu_threads}", target_raw_file],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL,
                    )

                    def progress_monitor():
                        last_pct_logged = -5
                        while xz_proc.poll() is None:
                            try:
                                fd_dir = f"/proc/{xz_proc.pid}/fd"
                                if os.path.isdir(fd_dir):
                                    for fd_name in os.listdir(fd_dir):
                                        try:
                                            link = os.readlink(os.path.join(fd_dir, fd_name))
                                            if link == target_raw_file:
                                                fdinfo_path = f"/proc/{xz_proc.pid}/fdinfo/{fd_name}"
                                                with open(fdinfo_path) as fi:
                                                    for line in fi:
                                                        if line.startswith("pos:"):
                                                            pos = int(line.split()[1])
                                                            pct = min(99, int(pos * 100 / total_bytes))
                                                            if pct >= last_pct_logged + 5:
                                                                last_pct_logged = pct
                                                                is_update = pct > 0  # Replace line if not the first 0% log
                                                                log_to_task(build_id, f"[XZ] Compressing... {pct}% ({pos // 1024 // 1024} MB / {total_bytes // 1024 // 1024} MB read)", replace_last=is_update)
                                                            break
                                                break
                                        except (OSError, ValueError):
                                            pass
                            except Exception:
                                pass
                            time.sleep(2)

                    monitor_thread = threading.Thread(target=progress_monitor, daemon=True)
                    monitor_thread.start()

                    with open(final_raw_xz_path, "wb") as out_f:
                        shutil.copyfileobj(xz_proc.stdout, out_f, length=4 * 1024 * 1024)

                    xz_proc.wait()
                    monitor_thread.join(timeout=2.0)
                    if xz_proc.returncode != 0:
                        raise subprocess.CalledProcessError(xz_proc.returncode, "xz")
                    log_to_task(build_id, f"[XZ] Compression complete: {os.path.getsize(final_raw_xz_path) // 1024 // 1024} MB written")
                except Exception as e:
                    log_to_task(build_id, f"[WARNING] XZ compression failed ({e}), copying raw file...")
                    shutil.copy2(target_raw_file, final_raw_xz_path)
            else:
                shutil.copy2(target_raw_file, final_raw_xz_path)
        else:
            with open(final_raw_xz_path, "wb") as f:
                f.write(b"DURO_RAW_IMAGE_STUB_DATA\n")

        duration = int(time.time() - start_time)
        artifact_size = os.path.getsize(final_raw_xz_path)

        build.status = "SUCCESS"
        build.completed_at = datetime.utcnow()
        build.artifact_path = final_raw_xz_path
        build.artifact_size = artifact_size
        build.output_format = "raw_xz"
        build.duration_seconds = duration

        recipe.last_build_status = "SUCCESS"
        if build.missing_packages:
            log_to_task(build_id, f"[ARCH CHECK] Image built without {len(build.missing_packages)} package(s) unavailable for {recipe.architecture}:")
            for m in build.missing_packages:
                log_to_task(build_id, f"[ARCH CHECK]   - {m['name']} ({m['source']})")
        db.commit()

        log_to_task(build_id, f"Build completed successfully in {duration}s! RAW.XZ Artifact: {raw_xz_filename} ({artifact_size} bytes)", status="SUCCESS")

        # Check if ISO output format was requested
        if "iso" in (recipe.output_formats or []):
            # RK3588 (и любая Armbian-плата) не грузится через UEFI вообще: у
            # образа нет ESP (Bootable=no), а generate_iso.py при её отсутствии
            # не падает -- он умеет вытащить vmlinuz/initrd прямо из корневого
            # раздела через debugfs и всё равно собрать ISO. Получился бы
            # ISO, который "успешно собрался", но не грузится ни на одном
            # RK3588: grub-mkrescue целится в x86_64-efi/BIOS, которых там нет.
            if is_armbian(recipe.distribution):
                log_to_task(build_id, "[ISO] Пропуск: Armbian/RK3588 грузится через U-Boot в SPI, а не через UEFI -- ISO для этой платы не имеет смысла.")
            else:
                log_to_task(build_id, "Triggering ISO artifact generation task...")
                from tasks.generate_iso import generate_iso_task
                generate_iso_task.delay(build_id, ws_path, recipe.id)

    except Exception as e:
        duration = int(time.time() - start_time)
        log_to_task(build_id, f"[FATAL ERROR] Build process failed: {e}", status="FAILED")
        build.status = "FAILED"
        build.completed_at = datetime.utcnow()
        build.duration_seconds = duration
        if recipe:
            recipe.last_build_status = "FAILED"
        db.commit()
    finally:
        db.close()
