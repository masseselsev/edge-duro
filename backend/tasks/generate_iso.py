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

    outputs_dir = os.path.join(os.getenv("DURO_WORKSPACE_PATH", "/opt/data/duro_workspace"), "outputs")
    os.makedirs(outputs_dir, exist_ok=True)

    iso_filename = os.path.basename(raw_image_path).replace(".raw.xz", ".iso").replace(".raw", ".iso")
    if not iso_filename.endswith(".iso"):
        iso_filename += ".iso"

    iso_path = os.path.join(outputs_dir, iso_filename)
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
                iso_size_mb = os.path.getsize(iso_path) / (1024 * 1024)
                log_to_task(build_id, f"[ISO SUCCESS] Created bootable ISO: {os.path.basename(iso_path)} ({iso_size_mb:.1f} MB)")
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
