import logging
import redis
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


def log_to_task(task_id: str, message: str, status: str = None) -> None:
    """
    Appends a log line to the specified Build record in the database
    and publishes to Redis PubSub for real-time SSE streaming.
    """
    from database import SessionLocal
    from models import Build
    from datetime import datetime

    db = SessionLocal()
    try:
        build = db.query(Build).filter(Build.id == task_id).first()
        if build:
            timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            log_line = f"[{timestamp}] {message}"
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

    # Publish to Redis PubSub channel
    try:
        redis_client.publish(f"build:{task_id}", message)
    except Exception as e:
        logger.error(f"Error publishing to Redis channel build:{task_id}: {e}")


from tasks.build_image import build_image_task
from tasks.generate_iso import generate_iso_task
from tasks.cleanup import workspace_cleanup_task
