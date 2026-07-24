import time
import logging
import redis
from datetime import datetime
from zoneinfo import ZoneInfo
from celery.schedules import crontab

from celery_app import celery_app, REDIS_URL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

redis_client = redis.Redis.from_url(REDIS_URL)

celery_app.conf.beat_schedule = {
    'workspace-cleanup-task': {
        'task': 'tasks.cleanup.workspace_cleanup_task',
        'schedule': crontab(hour=4, minute=0),  # Daily at 4 AM
    },
}
celery_app.conf.timezone = 'UTC'

_tz_cache = {"name": "UTC", "expires": 0.0}


def _get_tz_name() -> str:
    now = time.time()
    if now > _tz_cache["expires"]:
        from database import SessionLocal
        from models import Settings
        db = SessionLocal()
        try:
            settings = db.query(Settings).first()
            if settings and settings.timezone:
                _tz_cache["name"] = settings.timezone
        except Exception:
            pass
        finally:
            db.close()
        _tz_cache["expires"] = now + 30.0
    return _tz_cache["name"]


def log_to_task(task_id: str, message: str, status: str = None) -> None:
    if not message or not message.strip():
        return

    tz_name = _get_tz_name()
    try:
        timestamp_str = datetime.now(ZoneInfo(tz_name)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        timestamp_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    log_line = f"[{timestamp_str}] {message}"

    # 1. Publish to Redis PubSub INSTANTLY (<0.05ms, zero DB locks!)
    try:
        redis_client.publish(f"build:{task_id}", log_line)
    except Exception as e:
        logger.error(f"Error publishing to Redis channel build:{task_id}: {e}")

    # 2. Persist to PostgreSQL database asynchronously
    from database import SessionLocal
    from models import Build

    db = SessionLocal()
    try:
        build = db.query(Build).filter(Build.id == task_id).first()
        if build:
            build.log_output += f"{log_line}\n"
            if status:
                build.status = status
            elif build.status not in ("SUCCESS", "FAILED", "CANCELLED"):
                build.status = "RUNNING"
            db.commit()
    except Exception as e:
        logger.error(f"Error logging to build task {task_id}: {e}")
    finally:
        db.close()


from tasks.build_image import build_image_task
from tasks.generate_iso import generate_iso_task
from tasks.cleanup import workspace_cleanup_task
