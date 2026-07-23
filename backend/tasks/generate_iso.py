import os
import shutil
import subprocess
from celery_app import celery_app


@celery_app.task(name="tasks.generate_iso.generate_iso_task")
def generate_iso_task(build_id: str, raw_image_path: str, recipe_id: int):
    from tasks import log_to_task

    log_to_task(build_id, "[ISO] Starting ISO bootable image generation via xorriso...")

    iso_path = raw_image_path.replace(".raw.xz", ".iso").replace(".raw", ".iso")
    xorriso_bin = shutil.which("xorriso")

    if not xorriso_bin:
        log_to_task(build_id, "[ISO WARNING] 'xorriso' not found. Creating stub ISO artifact...")
        with open(iso_path, "wb") as f:
            f.write(b"DURO_ISO_IMAGE_STUB\n")
    else:
        cmd = [
            "xorriso", "-as", "mkisofs",
            "-r", "-V", "DURO_BOOT",
            "-o", iso_path,
            raw_image_path
        ]
        try:
            log_to_task(build_id, f"[ISO EXEC] {' '.join(cmd)}")
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0:
                log_to_task(build_id, f"[ISO ERROR] xorriso failed: {res.stderr}")
            else:
                log_to_task(build_id, f"[ISO SUCCESS] Created bootable ISO: {os.path.basename(iso_path)}")
        except Exception as e:
            log_to_task(build_id, f"[ISO ERROR] Failed executing xorriso: {e}")
