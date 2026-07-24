import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import get_db, setup_db_logging, engine
import models
from version import VERSION

# Routers
from routers import users as users_router
from routers import settings as settings_router
from routers import health as health_router
from routers import recipes as recipes_router
from routers import builds as builds_router
from routers import assets as assets_router
from routers import repositories as repositories_router

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
app.include_router(recipes_router.router)
app.include_router(builds_router.router)
app.include_router(assets_router.router)
app.include_router(repositories_router.router)


@app.on_event("startup")
def startup_db_init():
    try:
        models.Base.metadata.create_all(bind=engine)
        print("Database tables verified/created.")
    except Exception as e:
        print(f"Error creating database tables: {e}")

    try:
        setup_db_logging()
    except Exception as e:
        print(f"Error setting up database logging on startup: {e}")

    try:
        db = next(get_db())
        run_migrations_safety(db)
        upgrade_settings(db)
        seed_superadmin(db)
        seed_default_debian12_recipe(db)
        clear_stale_builds(db)
        db.close()
    except Exception as e:
        print(f"Error during database startup initialization: {e}")


def run_migrations_safety(db: Session):
    """
    Ensure newly added columns exist in PostgreSQL database directly.
    """
    try:
        db.execute(text("ALTER TABLE recipes ADD COLUMN IF NOT EXISTS kernel_params VARCHAR;"))
        db.execute(text("ALTER TABLE recipes ADD COLUMN IF NOT EXISTS raw_firstboot TEXT;"))
        db.commit()
    except Exception as e:
        print(f"Safety migration warning: {e}")


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


def seed_default_debian12_recipe(db: Session):
    """
    Seeds/updates default Debian 12 Bookworm base recipe with official Edge vitcompany repositories.
    """
    repos_spec = [
        {
            "name": "debian-main",
            "url": "http://deb.debian.org/debian",
            "suite": "bookworm",
            "components": "main contrib non-free non-free-firmware",
            "gpg_key_filename": "debian-archive-bookworm.gpg"
        },
        {
            "name": "edge-stable",
            "url": "http://edge.vitcompany.com/repo/bookworm/stable",
            "suite": "bookworm",
            "components": "main",
            "gpg_key_filename": "edge-archive-keyring.gpg"
        },
        {
            "name": "edge-testing",
            "url": "http://edge.vitcompany.com/repo/bookworm/testing",
            "suite": "bookworm",
            "components": "main",
            "gpg_key_filename": "edge-archive-keyring.gpg"
        }
    ]

    preseed_content = """# Debian Installer Preseed Configuration for Edge Debian 12
d-i apt-setup/no_mirror boolean true
d-i apt-setup/cdrom/set-next boolean false
d-i apt-setup/cdrom/set-failed boolean false
d-i console-setup/ask_detect boolean false
d-i console-setup/layoutcode string us
d-i partman-basicfilesystems/no_swap boolean false
d-i debian-installer/language string en
d-i debian-installer/country string UA
d-i debian-installer/locale string C
d-i debian-installer/keymap select us
d-i keymap select us
d-i console-keymaps-at/keymap select us
d-i keyboard-configuration/xkb-keymap select us
d-i netcfg/choose_interface select auto
d-i netcfg/link_wait_timeout string 10
d-i netcfg/dhcp_timeout string 90
d-i netcfg/get_hostname string edge-node
d-i netcfg/get_domain string local
"""

    postinst_content = """update-locale LANG=C.UTF-8
rm -f /etc/machine-id

cat << 'EOF' > /etc/apt/sources.list.d/edge.list
deb http://edge.vitcompany.com/repo/bookworm/stable bookworm main
#deb http://edge.vitcompany.com/repo/bookworm/testing bookworm main
EOF
"""

    firstboot_content = """#!/bin/sh
log() {
  echo "$(date --rfc-3339=seconds) [firstboot] $1" >> /var/log/edge/firstboot.log
}

log "EXEC"
systemd-machine-id-setup
log "DONE"
"""

    existing = db.query(models.Recipe).filter(models.Recipe.name == "Debian 12 Bookworm (Edge Base)").first()
    if not existing:
        recipe = models.Recipe(
            name="Debian 12 Bookworm (Edge Base)",
            description="Default Edge base OS image recipe for Debian 12 Bookworm (x86_64) with intel graphics, edge.vitcompany.com APT repositories, systemd firstboot, and core utilities.",
            distribution="debian",
            release="bookworm",
            architecture="amd64",
            output_formats=["raw_xz", "iso"],
            packages=[
                "systemd", "systemd-sysv", "dbus", "iproute2", "curl", "wget",
                "openssh-server", "firmware-misc-nonfree", "intel-media-va-driver-non-free",
                "linux-image-amd64", "net-tools", "sudo", "ca-certificates"
            ],
            repositories=repos_spec,
            hostname="edge-node",
            ssh_keys=[],
            kernel_params="ipv6.disable=1 nohz=off",
            raw_mkosi_conf="",
            raw_preseed_cfg=preseed_content,
            raw_postinst=postinst_content,
            raw_firstboot=firstboot_content
        )
        db.add(recipe)
        db.commit()
        print("Default Debian 12 Bookworm base recipe seeded successfully.")
    else:
        # Update repositories & scripts on existing template if missing vitcompany repos
        existing.repositories = repos_spec
        existing.raw_postinst = postinst_content
        existing.raw_preseed_cfg = preseed_content
        existing.raw_firstboot = firstboot_content
        existing.kernel_params = "ipv6.disable=1 nohz=off"
        db.commit()
        print("Updated existing Debian 12 Bookworm base recipe with edge.vitcompany.com repositories.")


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
