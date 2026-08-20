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
from routers import storage as storage_router

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
app.include_router(storage_router.router)


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
        db.execute(text("ALTER TABLE recipes ADD COLUMN IF NOT EXISTS timezone VARCHAR DEFAULT 'UTC';"))
        db.execute(text("ALTER TABLE recipes ADD COLUMN IF NOT EXISTS hostname_from_netif BOOLEAN DEFAULT FALSE;"))
        db.execute(text("ALTER TABLE recipes ADD COLUMN IF NOT EXISTS partitions JSON DEFAULT '[]'::json;"))
        db.execute(text("ALTER TABLE recipes ADD COLUMN IF NOT EXISTS root_password VARCHAR;"))
        db.execute(text("ALTER TABLE recipes ADD COLUMN IF NOT EXISTS users JSON DEFAULT '[]'::json;"))
        db.execute(text("ALTER TABLE recipes ADD COLUMN IF NOT EXISTS is_dev BOOLEAN DEFAULT FALSE;"))
        db.execute(text("ALTER TABLE recipes ADD COLUMN IF NOT EXISTS locale VARCHAR DEFAULT 'C.UTF-8';"))
        db.execute(text("ALTER TABLE recipes ADD COLUMN IF NOT EXISTS ssh_port INTEGER DEFAULT 2222;"))
        db.execute(text("ALTER TABLE recipes ADD COLUMN IF NOT EXISTS ignore_missing_arch_packages BOOLEAN DEFAULT FALSE;"))
        db.execute(text("ALTER TABLE recipes ADD COLUMN IF NOT EXISTS board VARCHAR DEFAULT 'generic';"))
        db.execute(text("ALTER TABLE recipes ADD COLUMN IF NOT EXISTS ssh_password_auth BOOLEAN DEFAULT TRUE;"))
        db.execute(text("ALTER TABLE recipes ADD COLUMN IF NOT EXISTS ssh_permit_root_login BOOLEAN DEFAULT FALSE;"))
        db.execute(text("ALTER TABLE builds ADD COLUMN IF NOT EXISTS missing_packages JSON DEFAULT '[]'::json;"))
        db.execute(text("ALTER TABLE settings ADD COLUMN IF NOT EXISTS log_retention_days INTEGER DEFAULT 3;"))
        db.execute(text("ALTER TABLE builds ADD COLUMN IF NOT EXISTS iso_artifact_path VARCHAR;"))
        db.execute(text("ALTER TABLE builds ADD COLUMN IF NOT EXISTS iso_artifact_size BIGINT;"))
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
    Seeds/updates default Debian 12 Bookworm base recipe with official Edge vitcompany repositories and Edge packages.
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
            "url": "https://edge.vitcompany.com/repo/bookworm/stable",
            "suite": "bookworm",
            "components": "main",
            "gpg_key_filename": "edge-archive-keyring.gpg"
        },
        {
            "name": "edge-testing",
            "url": "https://edge.vitcompany.com/repo/bookworm/testing",
            "suite": "bookworm",
            "components": "main",
            "gpg_key_filename": "edge-archive-keyring.gpg"
        }
    ]

    edge_base_pkgs = [
        "systemd", "systemd-sysv", "systemd-boot", "dbus", "iproute2", "curl", "wget",
        "openssh-server", "firmware-misc-nonfree", "intel-microcode", "firmware-sof-signed", "intel-media-va-driver-non-free",
        "linux-image-amd64", "net-tools", "sudo", "ca-certificates", "locales",
        "nginx-full", "gstreamer1.0-libav", "gstreamer1.0-plugins-good", "gstreamer1.0-plugins-bad",
        "gstreamer1.0-plugins-ugly", "gstreamer1.0-vaapi", "libturbojpeg0", "zip", "unzip",
        "rsyslog", "usbutils", "libmodbus5", "libgomp1", "resolvconf", "openvpn", "zabbix-agent",
        "sysstat", "jq", "htop", "btop", "iputils-ping", "traceroute", "bind9-dnsutils", "ethtool",
        "tcpdump", "iperf3", "pciutils", "strace", "lsof",
        "edge-base", "edge-target-tools", "edge-python3-psuctl", "acpi-support-base",
        "dbus-user-session", "python3-requests"
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

    # Locale is now a first-class recipe field applied by populate_extra_tree,
    # so the seed no longer hardcodes update-locale here.
    postinst_content = """rm -f /etc/machine-id
"""

    firstboot_content = """#!/bin/sh
log() {
  echo "$(date --rfc-3339=seconds) [firstboot] $1" >> /var/log/edge/firstboot.log
}

log "EXEC"
systemd-machine-id-setup
log "DONE"
"""

    # Upgrade any existing recipes to use HTTPS for vitcompany URLs
    all_recipes = db.query(models.Recipe).all()
    for r in all_recipes:
        if r.repositories and isinstance(r.repositories, list):
            updated_repos = []
            modified = False
            for repo in r.repositories:
                if isinstance(repo, dict):
                    url = repo.get("url", "")
                    if url.startswith("http://edge.vitcompany.com"):
                        repo["url"] = url.replace("http://edge.vitcompany.com", "https://edge.vitcompany.com")
                        modified = True
                updated_repos.append(repo)
            if modified:
                r.repositories = updated_repos
                db.commit()

    existing = db.query(models.Recipe).filter(models.Recipe.name == "Debian 12 Bookworm (Edge Base)").first()
    if not existing:
        recipe = models.Recipe(
            name="Debian 12 Bookworm (Edge Base)",
            description="Default Edge base OS image recipe for Debian 12 Bookworm (x86_64) with intel graphics, edge.vitcompany.com APT repositories, systemd firstboot, and core Edge packages.",
            distribution="debian",
            release="bookworm",
            architecture="amd64",
            output_formats=["raw_xz", "iso"],
            packages=edge_base_pkgs,
            repositories=repos_spec,
            hostname="edge-node",
            ssh_keys=[],
            ssh_port=2222,
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
        current_pkgs = list(existing.packages or [])
        for ep in ["edge-base", "edge-target-tools", "edge-python3-psuctl", "acpi-support-base", "dbus-user-session", "python3-requests", "htop", "btop", "iputils-ping", "traceroute", "bind9-dnsutils", "ethtool", "tcpdump", "iperf3", "pciutils"]:
            if ep not in current_pkgs:
                current_pkgs.append(ep)
        existing.packages = current_pkgs
        existing.repositories = repos_spec
        existing.raw_postinst = postinst_content
        existing.raw_preseed_cfg = preseed_content
        existing.raw_firstboot = firstboot_content
        existing.kernel_params = "ipv6.disable=1 nohz=off"
        db.commit()
        print("Updated existing Debian 12 Bookworm base recipe with Edge packages and vitcompany repositories.")


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
