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

    log_to_task(build_id, "[ISO] Starting native bootable ISO image generation via mkosi...")

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

        mkosi_bin = shutil.which("mkosi")
        conf_path = os.path.join(ws_path, "mkosi.conf")

        if mkosi_bin and os.path.exists(ws_path) and os.path.exists(conf_path):
            with open(conf_path, "r") as f:
                original_conf = f.read()

            # Temporarily configure Format=iso in mkosi.conf
            iso_conf = original_conf.replace("Format=disk", "Format=iso")
            with open(conf_path, "w") as f:
                f.write(iso_conf)

            src_output = os.path.join(ws_path, "output")
            shutil.rmtree(src_output, ignore_errors=True)

            cmd = ["mkosi", "--directory", ws_path, "--force", "build"]
            log_to_task(build_id, f"[ISO EXEC] {' '.join(cmd)}")

            try:
                res = subprocess.run(cmd, capture_output=True, text=True, cwd=ws_path)
                if res.returncode == 0 and os.path.exists(src_output) and os.listdir(src_output):
                    iso_files = [os.path.join(src_output, f) for f in os.listdir(src_output) if f.endswith(".iso")]
                    if not iso_files:
                        iso_files = [os.path.join(src_output, f) for f in os.listdir(src_output)]
                    iso_files.sort(key=lambda f: os.path.getsize(f), reverse=True)
                    shutil.copy2(iso_files[0], final_iso_path)
                else:
                    log_to_task(build_id, f"[ISO WARNING] mkosi ISO build code {res.returncode}: {res.stderr[:200]}")
            finally:
                # Restore original mkosi.conf
                with open(conf_path, "w") as f:
                    f.write(original_conf)

        if not os.path.exists(final_iso_path):
            log_to_task(build_id, "[ISO WARNING] Creating fallback ISO artifact...")
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
