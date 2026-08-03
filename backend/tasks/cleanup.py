import os
import shutil
from database import SessionLocal
from models import Recipe
from celery_app import celery_app
from core.workspace_cleanup import orphaned_workspaces


@celery_app.task(name="tasks.cleanup.workspace_cleanup_task")
def workspace_cleanup_task():
    """
    Cleans up orphaned workspace directories for deleted recipes.

    Which directories qualify is decided by core.workspace_cleanup, which keeps
    the rule testable -- the cost of a mistake here is an rmtree over the wrong
    directory. It used to be "everything except outputs", which took the
    package caches with it on every nightly run.
    """
    db = SessionLocal()
    try:
        active_ids = {str(r.id) for r in db.query(Recipe.id).all()}
        ws_base = os.getenv("DURO_WORKSPACE_PATH", "/opt/data/duro_workspace")

        if not os.path.exists(ws_base):
            return

        entries = [item for item in os.listdir(ws_base)
                   if os.path.isdir(os.path.join(ws_base, item))]

        for item in orphaned_workspaces(entries, active_ids):
            item_path = os.path.join(ws_base, item)
            print(f"[CLEANUP] Removing orphaned workspace directory: {item_path}")
            shutil.rmtree(item_path, ignore_errors=True)
    except Exception as e:
        print(f"[CLEANUP ERROR] Failed running workspace cleanup task: {e}")
    finally:
        db.close()
