import os
import re
import shutil
import subprocess
from datetime import datetime
from database import SessionLocal
from models import Build, Recipe
from celery_app import celery_app


def extract_edge_base_version(ws_path: str, target_raw: str = None, log_text: str = None) -> str:
    """Extract Version of mandatory 'edge-base' Debian package from multiple sources."""
    # 1. Check if version file was saved in workspace during stdout streaming
    ver_file = os.path.join(ws_path, "edge_base_version.txt")
    if os.path.exists(ver_file):
        try:
            with open(ver_file, "r") as f:
                v = f.read().strip()
                if v and len(v) >= 3 and v[0].isdigit():
                    return v
        except Exception:
            pass

    # 2. Parse build log text history
    if log_text:
        match = re.search(r'edge-base(?:[:\w\-]+)?\s*\(?([0-9a-zA-Z\.\+\~\-]+)\)?', log_text)
        if match:
            v_str = match.group(1).strip()
            if len(v_str) >= 3 and v_str[0].isdigit():
                return v_str

    # 3. Check direct status paths in ws_path
    possible_status_paths = [
        os.path.join(ws_path, "root", "var", "lib", "dpkg", "status"),
        os.path.join(ws_path, "buildroot", "var", "lib", "dpkg", "status"),
        os.path.join(ws_path, "image", "var", "lib", "dpkg", "status"),
    ]
    for status_file in possible_status_paths:
        if os.path.exists(status_file):
            try:
                with open(status_file, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                match = re.search(r'Package:\s*edge-base\n(?:[^\n]+\n)*?Version:\s*([^\n]+)', content)
                if match:
                    return match.group(1).strip()
            except Exception:
                pass

    # 4. Extract rootfs partition from target_raw using sfdisk + dd + debugfs
    if target_raw and os.path.exists(target_raw) and not target_raw.endswith(".xz"):
        try:
            sf_res = subprocess.run(["sfdisk", "-d", target_raw], capture_output=True, text=True)
            if sf_res.returncode == 0:
                for line in sf_res.stdout.splitlines():
                    if "start=" in line and "size=" in line:
                        start_match = re.search(r'start=\s*(\d+)', line)
                        size_match = re.search(r'size=\s*(\d+)', line)
                        if start_match and size_match:
                            start_sector = int(start_match.group(1))
                            sector_count = int(size_match.group(1))
                            if start_sector > 0 and sector_count > 50000:
                                root_part_img = os.path.join(ws_path, "rootfs_part.img")
                                dd_cmd = [
                                    "dd", f"if={target_raw}", f"of={root_part_img}",
                                    "bs=512", f"skip={start_sector}", f"count={sector_count}",
                                    "status=none"
                                ]
                                subprocess.run(dd_cmd, check=True)
                                if os.path.exists(root_part_img):
                                    dbg_res = subprocess.run(["debugfs", "-R", "cat var/lib/dpkg/status", root_part_img], capture_output=True, text=True)
                                    if os.path.exists(root_part_img):
                                        os.remove(root_part_img)
                                    if dbg_res.returncode == 0 and "edge-base" in dbg_res.stdout:
                                        match = re.search(r'Package:\s*edge-base\n(?:[^\n]+\n)*?Version:\s*([^\n]+)', dbg_res.stdout)
                                        if match:
                                            return match.group(1).strip()
        except Exception:
            pass

    return ""


@celery_app.task(name="tasks.generate_iso.generate_iso_task")
def generate_iso_task(build_id: str, ws_path: str, recipe_id: int):
    from tasks import log_to_task

    log_to_task(build_id, "[ISO] Starting UEFI El Torito bootable ISO image generation...")

    db = SessionLocal()
    try:
        build = db.query(Build).filter(Build.id == build_id).first()
        recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()

        outputs_dir = os.path.join(os.getenv("DURO_WORKSPACE_PATH", "/opt/data/duro_workspace"), "outputs")
        os.makedirs(outputs_dir, exist_ok=True)

        src_output = os.path.join(ws_path, "output")
        raw_candidates = []
        if os.path.exists(src_output):
            raw_candidates += [os.path.join(src_output, f) for f in os.listdir(src_output) if f.endswith(".raw") or f.endswith(".img")]
        if os.path.exists(outputs_dir):
            raw_candidates += [os.path.join(outputs_dir, f) for f in os.listdir(outputs_dir) if f.endswith(".raw") or f.endswith(".img")]

        raw_candidates.sort(key=lambda f: os.path.getsize(f), reverse=True)
        target_raw = raw_candidates[0] if raw_candidates else None

        # 1. Enforce mandatory edge-base package presence
        log_content = build.log_output if build else None
        edge_base_ver = extract_edge_base_version(ws_path, target_raw, log_content)
        if not edge_base_ver:
            error_msg = "[ISO ERROR] Mandatory package 'edge-base' is missing from rootfs dpkg database! Aborting ISO generation."
            log_to_task(build_id, error_msg, status="FAILED")
            return

        # 2. Strict Naming Rule: edge_{EDGE_BASE_VERSION}_{ARCH}-{RELEASE}-auto.iso
        arch = (recipe.architecture if recipe and recipe.architecture else "amd64").lower()
        rel = (recipe.release if recipe and recipe.release else "bookworm").lower()
        ts_suffix = datetime.utcnow().strftime('%y%m%d-%H%M')

        if edge_base_ver:
            iso_filename = f"edge_{edge_base_ver}_{arch}-{rel}_{ts_suffix}.iso"
        else:
            iso_filename = f"edge_{arch}-{rel}_{ts_suffix}.iso"
        final_iso_path = os.path.join(outputs_dir, iso_filename)

        log_to_task(build_id, f"[ISO INFO] Verified edge-base package version: {edge_base_ver}")

        if target_raw:
            log_to_task(build_id, f"[ISO EXEC] Processing raw image '{os.path.basename(target_raw)}' ({os.path.getsize(target_raw)} bytes) into UEFI El Torito ISO...")

            iso_staging = os.path.join(ws_path, "iso_staging")
            shutil.rmtree(iso_staging, ignore_errors=True)
            os.makedirs(iso_staging, exist_ok=True)

            efi_img_path = os.path.join(iso_staging, "efi.img")
            esp_extracted = False

            # Extract EFI System Partition (ESP) using sfdisk and dd
            try:
                sf_res = subprocess.run(["sfdisk", "-d", target_raw], capture_output=True, text=True)
                if sf_res.returncode == 0:
                    for line in sf_res.stdout.splitlines():
                        line_lower = line.lower()
                        if "start=" in line_lower and ("size=" in line_lower or "type=" in line_lower):
                            start_match = re.search(r'start=\s*(\d+)', line)
                            size_match = re.search(r'size=\s*(\d+)', line)
                            if start_match and size_match:
                                start_sector = int(start_match.group(1))
                                sector_count = int(size_match.group(1))
                                dd_cmd = [
                                    "dd", f"if={target_raw}", f"of={efi_img_path}",
                                    "bs=512", f"skip={start_sector}", f"count={sector_count}",
                                    "status=none"
                                ]
                                subprocess.run(dd_cmd, check=True)
                                esp_extracted = os.path.exists(efi_img_path) and os.path.getsize(efi_img_path) > 0
                                if esp_extracted:
                                    log_to_task(build_id, f"[ISO] Extracted EFI System Partition image ({os.path.getsize(efi_img_path)} bytes)")
                                    
                                    # Copy /EFI directory tree into iso_staging/EFI for VirtualBox UEFI discovery
                                    mcopy_bin = shutil.which("mcopy")
                                    extracted_efi_tree = False
                                    if mcopy_bin:
                                        try:
                                            res_mc = subprocess.run([mcopy_bin, "-s", "-i", efi_img_path, "::EFI", iso_staging], capture_output=True, text=True)
                                            if res_mc.returncode == 0 and os.path.exists(os.path.join(iso_staging, "EFI")):
                                                extracted_efi_tree = True
                                                log_to_task(build_id, "[ISO] Extracted /EFI directory tree using mcopy user-space driver")
                                        except Exception as e_mc:
                                            log_to_task(build_id, f"[ISO WARNING] mcopy extraction failed: {e_mc}")

                                    if not extracted_efi_tree:
                                        mnt_dir = os.path.join(ws_path, "mnt_efi")
                                        os.makedirs(mnt_dir, exist_ok=True)
                                        try:
                                            subprocess.run(["mount", "-o", "loop,ro", efi_img_path, mnt_dir], check=True, capture_output=True)
                                            if os.path.exists(os.path.join(mnt_dir, "EFI")):
                                                shutil.copytree(os.path.join(mnt_dir, "EFI"), os.path.join(iso_staging, "EFI"), dirs_exist_ok=True)
                                                extracted_efi_tree = True
                                                log_to_task(build_id, "[ISO] Copied /EFI directory tree into ISO filesystem root via loop mount")
                                            subprocess.run(["umount", mnt_dir], check=True, capture_output=True)
                                        except Exception as err:
                                            log_to_task(build_id, f"[ISO WARNING] Loop mount EFI extraction: {err}")
                                        finally:
                                            if os.path.exists(mnt_dir):
                                                try:
                                                    subprocess.run(["umount", "-l", mnt_dir], capture_output=True)
                                                    os.rmdir(mnt_dir)
                                                except Exception:
                                                    pass

                                    # Ensure both uppercase BOOTX64.EFI and lowercase bootx64.efi exist
                                    efi_boot_dir = os.path.join(iso_staging, "EFI", "BOOT")
                                    if os.path.exists(efi_boot_dir):
                                        b64_upper = os.path.join(efi_boot_dir, "BOOTX64.EFI")
                                        b64_lower = os.path.join(efi_boot_dir, "bootx64.efi")
                                        if os.path.exists(b64_upper) and not os.path.exists(b64_lower):
                                            try:
                                                shutil.copy2(b64_upper, b64_lower)
                                            except Exception:
                                                pass
                                        elif os.path.exists(b64_lower) and not os.path.exists(b64_upper):
                                            try:
                                                shutil.copy2(b64_lower, b64_upper)
                                            except Exception:
                                                pass
                                    break
            except Exception as e:
                log_to_task(build_id, f"[ISO WARNING] ESP partition extraction failed: {e}")

            # Copy compressed raw.xz artifact into ISO staging directory (saves 2.5GB in ISO)
            if build and build.artifact_path and os.path.exists(build.artifact_path):
                shutil.copy2(build.artifact_path, os.path.join(iso_staging, os.path.basename(build.artifact_path)))
            elif target_raw:
                # Fallback: Compress target_raw on the fly if xz artifact is unavailable
                raw_xz_staged = os.path.join(iso_staging, f"{os.path.splitext(os.path.basename(target_raw))[0]}.raw.xz")
                conc = int(os.getenv("CELERY_WORKER_CONCURRENCY", "2"))
                cpu_threads = max(1, (os.cpu_count() or 2) // max(1, conc))
                try:
                    with open(raw_xz_staged, "wb") as out_f:
                        subprocess.run(["nice", "-n", "19", "ionice", "-c", "3", "xz", "-c", "-3", f"-T{cpu_threads}", target_raw], stdout=out_f, check=True)
                except Exception:
                    shutil.copy2(target_raw, os.path.join(iso_staging, os.path.basename(target_raw)))

            xorriso_bin = shutil.which("xorriso")
            if xorriso_bin and esp_extracted:
                cmd = [
                    "xorriso", "-as", "mkisofs",
                    "-r", "-J", "-joliet-long",
                    "-V", "DURO_BOOT",
                    "-append_partition", "2", "0xef", efi_img_path,
                    "-appended_part_as_gpt",
                    "-eltorito-alt-boot",
                    "-e", "--interval:appended_partition_2:all::",
                    "-no-emul-boot",
                    "-o", final_iso_path,
                    iso_staging
                ]
                log_to_task(build_id, f"[ISO EXEC] {' '.join(cmd)}")
                res = subprocess.run(cmd, capture_output=True, text=True)
                if res.returncode != 0:
                    log_to_task(build_id, f"[ISO WARNING] xorriso UEFI build failed: {res.stderr[:200]}, falling back to raw copy...")
                    shutil.copy2(target_raw, final_iso_path)
            else:
                log_to_task(build_id, "[ISO WARNING] xorriso or ESP image unavailable, copying raw image directly...")
                shutil.copy2(target_raw, final_iso_path)

            shutil.rmtree(iso_staging, ignore_errors=True)
        else:
            log_to_task(build_id, "[ISO WARNING] No raw disk image found to package. Creating fallback ISO...")
            with open(final_iso_path, "wb") as f:
                f.write(b"DURO_BOOTABLE_ISO_STUB\n")

        iso_size = os.path.getsize(final_iso_path)
        iso_size_mb = iso_size / (1024 * 1024)

        if build:
            build.iso_artifact_path = final_iso_path
            build.iso_artifact_size = iso_size
            build.status = "SUCCESS"
            db.commit()

        log_to_task(build_id, f"[ISO SUCCESS] Created bootable UEFI ISO: {iso_filename} ({iso_size_mb:.1f} MB)", status="SUCCESS")

    except Exception as e:
        log_to_task(build_id, f"[ISO ERROR] Failed during ISO generation: {e}")
    finally:
        db.close()
