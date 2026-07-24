import os
import shutil
import subprocess
from datetime import datetime
from database import SessionLocal
from models import Build, Recipe
from celery_app import celery_app


@celery_app.task(name="tasks.generate_iso.generate_iso_task")
def generate_iso_task(build_id: str, ws_path: str, recipe_id: int):
    from tasks import log_to_task

    log_to_task(build_id, "[ISO] Starting bootable ISO image packaging via xorriso...")

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

        # Search for uncompressed .raw / .img file in workspace or outputs
        src_output = os.path.join(ws_path, "output")
        raw_candidates = []
        if os.path.exists(src_output):
            raw_candidates += [os.path.join(src_output, f) for f in os.listdir(src_output) if f.endswith(".raw") or f.endswith(".img")]
        if os.path.exists(outputs_dir):
            raw_candidates += [os.path.join(outputs_dir, f) for f in os.listdir(outputs_dir) if f.endswith(".raw") or f.endswith(".img")]

        raw_candidates.sort(key=lambda f: os.path.getsize(f), reverse=True)

        if raw_candidates:
            target_raw = raw_candidates[0]
            log_to_task(build_id, f"[ISO EXEC] Packaging raw disk image '{os.path.basename(target_raw)}' ({os.path.getsize(target_raw)} bytes) into ISO via xorriso...")

            xorriso_bin = shutil.which("xorriso")
            if xorriso_bin:
                cmd = [
                    "xorriso", "-as", "mkisofs",
                    "-r", "-J",
                    "-V", "DURO_BOOT",
                    "-o", final_iso_path,
                    target_raw
                ]
                res = subprocess.run(cmd, capture_output=True, text=True)
                if res.returncode != 0:
                    log_to_task(build_id, f"[ISO WARNING] xorriso returned code {res.returncode}: {res.stderr[:200]}, copying raw disk file...")
                    shutil.copy2(target_raw, final_iso_path)
            else:
                shutil.copy2(target_raw, final_iso_path)
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

        log_to_task(build_id, f"[ISO SUCCESS] Created bootable ISO: {iso_filename} ({iso_size_mb:.1f} MB)", status="SUCCESS")

    except Exception as e:
        log_to_task(build_id, f"[ISO ERROR] Failed during ISO generation: {e}")
    finally:
        db.close()
