import os
import shutil
from database import SessionLocal
from models import Recipe
from celery_app import celery_app


@celery_app.task(name="tasks.cleanup.workspace_cleanup_task")
def workspace_cleanup_task():
    """
    Cleans up orphaned workspace directories for deleted recipes.
    """
    db = SessionLocal()
    try:
        active_ids = {str(r.id) for r in db.query(Recipe.id).all()}
        ws_base = os.getenv("DURO_WORKSPACE_PATH", "/opt/data/duro_workspace")

        if not os.path.exists(ws_base):
            return

        for item in os.listdir(ws_base):
            if item == "outputs":
                continue
            item_path = os.path.join(ws_base, item)
            if os.path.isdir(item_path) and item not in active_ids:
                print(f"[CLEANUP] Removing orphaned workspace directory: {item_path}")
                shutil.rmtree(item_path, ignore_errors=True)
    except Exception as e:
        print(f"[CLEANUP ERROR] Failed running workspace cleanup task: {e}")
    finally:
        db.close()
