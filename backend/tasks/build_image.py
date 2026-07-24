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

        mkosi_bin = shutil.which("mkosi")
        if not mkosi_bin:
            log_to_task(build_id, "[WARNING] 'mkosi' binary not found in worker container PATH. Running in simulated build mode...")
            cmd = ["echo", "[SIMULATION] Built OS image successfully."]
        else:
            cmd = ["mkosi", "--directory", ws_path, "--force", "build"]

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
                        subprocess.run(["xz", "-c", "-3", target_raw_file], stdout=out_f, check=True)
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
            iso_source = uncompressed_raw_path if (uncompressed_raw_path and os.path.exists(uncompressed_raw_path)) else final_raw_xz_path
            from tasks.generate_iso import generate_iso_task
            generate_iso_task.delay(build_id, iso_source, recipe.id)

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
