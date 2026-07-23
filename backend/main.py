import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from database import get_db, setup_db_logging
import models
from version import VERSION

# Routers
from routers import users as users_router
from routers import settings as settings_router
from routers import health as health_router

app = FastAPI(title="Edge-D.U.R.O. API", version=VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users_router.router)
app.include_router(settings_router.router)
app.include_router(health_router.router)



@app.on_event("startup")
def startup_db_init():
    try:
        setup_db_logging()
    except Exception as e:
        print(f"Error setting up database logging on startup: {e}")

    try:
        db = next(get_db())
        upgrade_settings(db)
        seed_superadmin(db)
        clear_stale_builds(db)
        db.close()
    except Exception as e:
        print(f"Error during database startup initialization: {e}")


def seed_superadmin(db: Session):
    """
    Seeds the initial super administrator account if none exists.
    """
    import bcrypt

    username = os.getenv("SUPERADMIN_USERNAME") or "admin"
    password = os.getenv("ADMIN_PASSWORD") or "q1w2e3r4"

    superadmin = db.query(models.User).filter(models.User.is_superadmin == True).first()
    if not superadmin:
        pwd_bytes = password.encode('utf-8')
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(pwd_bytes, salt).decode('utf-8')
        db_user = models.User(
            username=username,
            hashed_password=hashed,
            name="Super Administrator",
            is_superadmin=True,
            comment="System-seeded superadmin"
        )
        db.add(db_user)
        db.commit()
        print(f"Superadmin user '{username}' seeded successfully.")


def upgrade_settings(db: Session):
    """
    Ensures default settings exist in the database.
    """
    settings = db.query(models.Settings).first()
    if not settings:
        settings = models.Settings()
        db.add(settings)
        db.commit()
        print("Default settings initialized.")


def clear_stale_builds(db: Session):
    """
    Clear any builds left in RUNNING state on startup.
    """
    try:
        stale_builds = db.query(models.Build).filter(models.Build.status == "RUNNING").all()
        for build in stale_builds:
            build.status = "FAILED"
            build.log_output = (build.log_output or "") + "\n[SYSTEM] Build interrupted due to service restart."
        db.commit()
        if stale_builds:
            print(f"Cleared {len(stale_builds)} stale running builds on startup.")
    except Exception as e:
        print(f"Error clearing stale builds: {e}")
