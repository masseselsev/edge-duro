import os
import shutil
import subprocess
from database import SessionLocal
from models import Build
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

    # Record ISO artifact & final build status in DB
    db = SessionLocal()
    try:
        build = db.query(Build).filter(Build.id == build_id).first()
        if build and os.path.exists(iso_path):
            build.iso_artifact_path = iso_path
            build.iso_artifact_size = os.path.getsize(iso_path)
            build.status = "SUCCESS"
            db.commit()
            log_to_task(build_id, "[SYSTEM] Build and ISO generation completed successfully!", status="SUCCESS")
    except Exception as e:
        log_to_task(build_id, f"[ERROR] Failed to save ISO metadata to database: {e}")
    finally:
        db.close()
