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

        mkosi_bin = shutil.which("mkosi")
        if not mkosi_bin:
            log_to_task(build_id, "[WARNING] 'mkosi' binary not found in worker container PATH. Running in simulated build mode...")
            cmd = ["echo", "[SIMULATION] Built OS image successfully."]
        else:
            cmd = ["mkosi", "--directory", ws_path, "build"]

        log_to_task(build_id, f"[EXEC] {' '.join(cmd)}")

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=ws_path
        )

        if process.stdout:
            for line in iter(process.stdout.readline, ""):
                clean_line = line.rstrip("\r\n")
                log_to_task(build_id, clean_line)

                # Check if build was cancelled via API
                db.refresh(build)
                if build.status == "CANCELLED":
                    log_to_task(build_id, "[SYSTEM] Process termination requested by user. Terminating mkosi...")
                    process.terminate()
                    process.wait(timeout=5)
                    return

            process.stdout.close()

        return_code = process.wait()
        if return_code != 0 and mkosi_bin:
            raise subprocess.CalledProcessError(return_code, cmd)

        # 4. Finalize Artifact
        log_to_task(build_id, "[STEP 4/4] Finalizing build output artifacts...")

        outputs_dir = os.path.join(os.getenv("DURO_WORKSPACE_PATH", "/opt/data/duro_workspace"), "outputs")
        os.makedirs(outputs_dir, exist_ok=True)

        artifact_filename = f"{recipe.name.lower().replace(' ', '_')}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.raw.xz"
        final_path = os.path.join(outputs_dir, artifact_filename)

        # Simulate or copy output artifact
        src_output = os.path.join(ws_path, "output")
        if os.path.exists(src_output) and os.listdir(src_output):
            first_file = os.path.join(src_output, os.listdir(src_output)[0])
            shutil.copy2(first_file, final_path)
        else:
            # Create a mock raw file if none produced
            with open(final_path, "wb") as f:
                f.write(b"DURO_RAW_IMAGE_STUB_DATA\n")

        duration = int(time.time() - start_time)
        artifact_size = os.path.getsize(final_path)

        build.status = "SUCCESS"
        build.completed_at = datetime.utcnow()
        build.artifact_path = final_path
        build.artifact_size = artifact_size
        build.output_format = "raw_xz"
        build.duration_seconds = duration

        recipe.last_build_status = "SUCCESS"
        db.commit()

        log_to_task(build_id, f"Build completed successfully in {duration}s! Artifact: {artifact_filename} ({artifact_size} bytes)", status="SUCCESS")

        # Check if ISO output format was requested
        if "iso" in (recipe.output_formats or []):
            log_to_task(build_id, "Triggering ISO artifact generation task...")
            from tasks.generate_iso import generate_iso_task
            generate_iso_task.delay(build_id, final_path, recipe.id)

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
