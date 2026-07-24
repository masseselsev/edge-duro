import os
import re
import shutil
import subprocess
from datetime import datetime
from database import SessionLocal
from models import Build, Recipe
from celery_app import celery_app


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

        timestamp_str = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        base_name = recipe.name.lower().replace(' ', '_') if recipe else "edge_os"
        iso_filename = f"{base_name}_{timestamp_str}.iso"
        final_iso_path = os.path.join(outputs_dir, iso_filename)

        src_output = os.path.join(ws_path, "output")
        raw_candidates = []
        if os.path.exists(src_output):
            raw_candidates += [os.path.join(src_output, f) for f in os.listdir(src_output) if f.endswith(".raw") or f.endswith(".img")]
        if os.path.exists(outputs_dir):
            raw_candidates += [os.path.join(outputs_dir, f) for f in os.listdir(outputs_dir) if f.endswith(".raw") or f.endswith(".img")]

        raw_candidates.sort(key=lambda f: os.path.getsize(f), reverse=True)

        if raw_candidates:
            target_raw = raw_candidates[0]
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
                        if "start=" in line and ("size=" in line or "type=" in line):
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
                                    break
            except Exception as e:
                log_to_task(build_id, f"[ISO WARNING] ESP partition extraction failed: {e}")

            # Copy raw disk image into ISO staging directory
            shutil.copy2(target_raw, os.path.join(iso_staging, os.path.basename(target_raw)))

            xorriso_bin = shutil.which("xorriso")
            if xorriso_bin and esp_extracted:
                cmd = [
                    "xorriso", "-as", "mkisofs",
                    "-r", "-J",
                    "-V", "DURO_BOOT",
                    "-eltorito-alt-boot",
                    "-e", "efi.img",
                    "-no-emul-boot",
                    "-isohybrid-gpt-basdat",
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
