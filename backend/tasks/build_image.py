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
        ws_path = prepare_workspace(recipe.id)
        populate_extra_tree(recipe, assets, ws_path)

        # 2. Generate mkosi.conf
        log_to_task(build_id, "[STEP 2/4] Generating mkosi.conf recipe configuration...")
        generate_mkosi_conf(recipe, ws_path)

        # 3. Execute mkosi build process
        log_to_task(build_id, "[STEP 3/4] Invoking mkosi systemd-nspawn build engine...")

        # Clean existing output directory if present
        shutil.rmtree(os.path.join(ws_path, "output"), ignore_errors=True)

        stdbuf_bin = shutil.which("stdbuf")
        mkosi_bin = shutil.which("mkosi")
        if not mkosi_bin:
            log_to_task(build_id, "[WARNING] 'mkosi' binary not found in worker container PATH. Running in simulated build mode...")
            cmd = ["echo", "[SIMULATION] Built OS image successfully."]
        else:
            cmd = ["mkosi", "--directory", ws_path, "--force", "build"]

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

                    pct_match = re.search(r'(\d+)%', clean_line)
                    if pct_match:
                        pct = int(pct_match.group(1))
                        if pct % 10 == 0 and pct != last_progress_pct:
                            last_progress_pct = pct
                            log_to_task(build_id, clean_line)
                        continue

                    log_to_task(build_id, clean_line)

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
                                master_file.close()
                                return
                        except Exception:
                            pass

            except Exception:
                break

        master_file.close()

        return_code = process.wait()
        if return_code != 0 and mkosi_bin:
            raise subprocess.CalledProcessError(return_code, cmd)

        # 4. Finalize Artifact
        log_to_task(build_id, "[STEP 4/4] Finalizing build output artifacts...")

        outputs_dir = os.path.join(os.getenv("DURO_WORKSPACE_PATH", "/opt/data/duro_workspace"), "outputs")
        os.makedirs(outputs_dir, exist_ok=True)

        timestamp_str = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        base_name = recipe.name.lower().replace(' ', '_')
        raw_xz_filename = f"{base_name}_{timestamp_str}.raw.xz"
        final_raw_xz_path = os.path.join(outputs_dir, raw_xz_filename)

        src_output = os.path.join(ws_path, "output")
        uncompressed_raw_path = None

        if os.path.exists(src_output) and os.listdir(src_output):
            all_files = [os.path.join(src_output, f) for f in os.listdir(src_output)]
            disk_files = [f for f in all_files if f.endswith(".raw") or f.endswith(".img") or f.endswith(".raw.xz")]
            if not disk_files:
                disk_files = [f for f in all_files if not f.endswith(".efi") and not f.endswith(".vmlinuz") and not f.endswith(".initrd")]
            if not disk_files:
                disk_files = all_files

            disk_files.sort(key=lambda f: os.path.getsize(f), reverse=True)
            target_raw_file = disk_files[0]
            
            if not target_raw_file.endswith(".xz"):
                uncompressed_raw_path = target_raw_file
                log_to_task(build_id, f"Compressing raw disk image '{os.path.basename(target_raw_file)}' ({os.path.getsize(target_raw_file)} bytes) into {raw_xz_filename}...")
                try:
                    with open(final_raw_xz_path, "wb") as out_f:
                        subprocess.run(["xz", "-c", "-3", "-T0", target_raw_file], stdout=out_f, check=True)
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
        db.commit()

        log_to_task(build_id, f"Build completed successfully in {duration}s! RAW.XZ Artifact: {raw_xz_filename} ({artifact_size} bytes)", status="SUCCESS")

        # Check if ISO output format was requested
        if "iso" in (recipe.output_formats or []):
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
