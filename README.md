# Edge D.U.R.O. (Debian & Ubuntu Recipe Oven)

Automated image-building factory of the Edge ecosystem. A web-based control plane and background job runner for `mkosi` allowing users to visually configure, manage, and execute OS image recipes for Debian 12+ and Ubuntu 22+ (amd64/arm64) to produce monolithic provisioning artifacts (`.raw.xz`, `.iso`).

Beyond generic amd64 images, recipes can target specific arm64 single-board computers — see [ARM64 Board Support](#-9-arm64-board-support-rk3588--orange-pi-5-plus) for the RK3588 / Orange Pi 5 Plus pipeline, which produces a self-provisioning microSD card that installs itself onto the board's NVMe.

---

## 🏗️ Architecture & Tech Stack

- **Backend:** Python 3.13, FastAPI, SQLAlchemy 2.0, Alembic, Celery, Redis, SSE log streaming.
- **Frontend:** React 19, TypeScript, Tailwind CSS 3, CodeMirror 6, Lucide Icons, Vite 8.
- **Database:** PostgreSQL 15.
- **Task Runner:** Celery Worker in privileged mode for `mkosi` systemd-nspawn build execution.
- **Deployment:** Docker Compose (6 isolated services).

---

## ✨ Recent Updates & Key System Features

### 📦 1. Dual-Card Visual Package Manager
The Web UI package selector divides packages into two interactive, searchable cards:
- **EDGE PLATFORM PACKAGES & DEPENDENCIES (Cyan Theme)**: Dedicated card for multiple Edge target suite chips (`edge-base`, `edge-target-tools`, `edge-python3-psuctl`, `edge-target-uralan`, `edge-target-kaskad4`, `edge-target-puma`, `edge-target-skif`, `edge-target-wspaces7`, `edge-target-wspaces9`, `edge-target-trc`, `edge-target-roadeye3`, `edge-target-edges`, `edge-target-edges4`, `edge-mvs`, `edge-timekeeper`, `edge-zabbix-agent`, etc.).
- **STANDARD SYSTEM & CUSTOM APT PACKAGES (Amber Theme)**: Dedicated card for standard distribution utilities (`systemd`, `linux-image-amd64`, `nginx-full`, `openvpn`, `jq`, `rsyslog`, `usbutils`, `libmodbus5`, etc.).
- Both cards merge dynamically into `recipe.packages` for full customization.

### 🔒 2. HTTPS Repository Protocol & 301 Redirect Resolution
- Official Edge repositories use `https://edge.vitcompany.com/repo/bookworm/stable` (and `testing`).
- Solved silent APT package resolution failures caused by `HTTP 301 Moved Permanently` redirects during non-interactive chroot builds.
- Includes automatic startup migration in `backend/main.py` that upgrades any existing database recipes from `http://` to `https://`.

### ⚡ 3. Direct Pre-Download & Local Overlay Installer (`repo_downloader.py`)
- Python-level package fetcher (`backend/core/repo_downloader.py`) parses `Packages.gz` indices from configured HTTPS repositories before `mkosi` runs.
- Pre-downloads `edge-base` and selected `edge-*` platform `.deb` packages straight into `mkosi.extra/opt/edge_packages/`.
- Installs packages deterministically inside the rootfs via `dpkg -i` during post-install execution, ensuring minimal reliance on host APT quirks.

### 🏷️ 4. Dynamic Hostname from Active Port MAC Address
- When `hostname_from_netif` is enabled, target system hostname is automatically set equal to the raw 12-character MAC address of the active network installation port in **lowercase without colons or delimiters** (e.g. `525400123456`).
- Executes during post-installation and persists via `edge-firstboot.service` systemd unit.

### 🏷️ 5. Strict Versioned Artifact Naming Rules (Timestamp Suffix)
Both **ISO** installer and **RAW.XZ** disk image output artifacts strictly adhere to the unified versioned naming scheme:
- **ISO Installer**: `edge_${EDGE_BASE_VERSION}_${ARCH}-${RELEASE}_${YYMMDD-HHMM}.iso`
  - *Example*: `edge_2026.3.0-18~testing+1371_amd64-bookworm_260729-1415.iso`
- **RAW.XZ Disk Image**: `edge_${EDGE_BASE_VERSION}_${ARCH}-${RELEASE}_${YYMMDD-HHMM}.raw.xz`
  - *Example*: `edge_2026.3.0-18~testing+1371_amd64-bookworm_260729-1415.raw.xz`

### 🧹 6. Log Stream Throttling & Workspace Purging
- Real-time PTY stdout stream filtering in `backend/tasks/build_image.py` throttles repetitive percentage lines to 10% step increments.
- `prepare_workspace` automatically purges stale script hooks (`mkosi.postinst`, `mkosi.finalize`, `mkosi.prepare`) before launching new builds.

### 🌐 7. Multi-Language Support (i18n)
- Full internationalization support in English (EN), Russian (RU), and Ukrainian (UK).

### 🧩 8. Architecture-Aware Package Skipping
- Before `mkosi` runs, every package a recipe resolves to is checked against the `binary-<arch>` indices of both the configured Edge repositories and the official distribution mirror. Index names are cached on disk for a day, so the multi-megabyte distribution index is fetched at most once per day rather than per build.
- With **Skip packages missing for this architecture** enabled on the recipe, unavailable packages are dropped from the build and listed per build in the history; without it the build fails in seconds with the exact list instead of dying inside `apt` minutes later. Both the pre-flight list and the end-of-build summary name every skipped package and where it came from, rather than only counting them.
- Packages required to boot (kernel, `apt`, `bash`, `systemd-boot`, …) are never skipped. `edge-*` packages are skippable, so an arm64 image builds before arm64 platform packages exist.
- An unreachable index means "unknown", not "missing": if any index fails to load the whole check is skipped, so a mirror outage can never silently drop packages from an image.
- When `apt` fails on a dependency the name-level check cannot see, the offending package names are parsed out of the log and appended to the same list.

### 🔧 9. ARM64 Board Support (RK3588 / Orange Pi 5 Plus)

Selecting **Armbian** as the distribution turns a recipe into an arm64 board build. Armbian is used as a *hardware layer*, not as a base system: the rootfs is still plain Debian or Ubuntu (chosen from the release), and only the parts that do not exist upstream come from `apt.armbian.com` — the Rockchip BSP kernel (`linux-image-vendor-rk35xx`), the matching DTB, and the board's U-Boot. The target board is picked in the recipe and is shown on the recipe card, in the build console, in build history and in storage.

- **Repository trust.** The Armbian signing key is fetched at build time and shipped into the image, so the source is added with `signed-by=` rather than `trusted=yes`, and `apt update` verifies the index both during the build and on the running board. `ca-certificates` and `gpgv` are always installed — without them the repo (which redirects to an HTTPS mirror) is silently unreachable inside the rootfs.
- **Bootloader.** Written into the built `.raw` by Armbian's own `platform_install.sh` taken from the image, so the idbloader/u-boot offsets are never duplicated here and cannot drift from upstream. A 16 MB unformatted partition reserves the area the RK3588 BootROM reads.
- **Firmware.** Blobs the board's drivers ask for by name (`rtl_nic/rtl8125b-2.fw` for the 2.5GbE ports, `rockchip/dptx.bin` for the USB-C DisplayPort output) are fetched individually from the upstream `linux-firmware` project and cached across builds, instead of pulling the ~655 MB `linux-firmware` package. They are placed before the initramfs is generated, so the initrd carries them too.

#### Card → NVMe provisioning

One microSD card provisions any number of boards. On first boot the card clones itself onto the NVMe, writes the bootloader into SPI NOR with `flashcp` (seconds, against minutes for a `dd` through `/dev/mtdblock0`), grows the last partition over the full disk, gives the clone its own machine-id and SSH host keys, and signals completion on the board's LED and console. The marker that provisioning succeeded lives on the *target*, never on the card, so the same card keeps working on the next board.

#### Which medium boots

A `dd` clone copies every identifier a filesystem and a partition table carry — label, filesystem UUID and PARTUUID alike — so after provisioning the card and the installed system are indistinguishable by any of them. To keep the choice deterministic, the image carries a **fixed root PARTUUID** that the loader entry names, and provisioning stamps the clone with a **fresh random one** and rewrites the clone's own loader entry to match:

- **Card inserted** → the card boots and re-images the NVMe from it. This is how a new image is tested on a board that is already provisioned.
- **No card** → the NVMe boots from its own PARTUUID.

> **Filesystem labels are deliberately left alone** (`edgeroot`, `edgeboot`, `edgelog`, `edgestor`) — the platform running on the installed system addresses its filesystems by them. Only the root *partition* UUID is made unique.
>
> A consequence worth knowing: `/etc/fstab` still mounts `/var/log/edge` and `/var/opt/edge` by label, and those labels exist on both media at once. **With a card inserted into a provisioned board, those two mounts may come from the card rather than from the NVMe.** This is accepted behaviour: it does not affect booting, and it does not affect re-imaging the NVMe, which addresses the target by device path. The card is a transit medium and is not meant to be run as a working system.

#### Written-card compatibility

Some card writers (Raspberry Pi Imager among them) expand the partition table onto the physical card after writing the image: they relocate the backup GPT to the end of the card and move `PartitionEntryLBA` in the primary header to `FirstUsableLBA - 32`, recomputing the header checksum but **not** moving the 16 KB entry array. The stored entry-array checksum then describes bytes nobody wrote — U-Boot tolerates this and falls back to the backup table, but Linux discards the table outright and the card enumerates no partitions at all. The build therefore places an identical copy of the entry array at that address as well, so the pointer lands on valid data wherever it ends up. The header itself is left untouched, and only zeroed space inside the bootloader gap is used.

#### Boot-time behaviour

`systemd-networkd-wait-online` is set to `--any`. It otherwise waits for *every* managed link, and on a two-port board with one cable plugged in that meant `network-online.target` — and everything ordered after it, including provisioning, which needs no network at all — stalled until the 120 s timeout on every boot.

---

## 🔌 Default Exposed Ports

| Service | Container Port | Host Port | Notes |
|---------|---------------|-----------|-------|
| **Frontend** | 3333 | `3333` | Web UI & Nginx API reverse proxy |
| **Backend** | 8000 | `8003` | FastAPI REST & SSE endpoints |
| **PostgreSQL** | 5432 | `5433` | Standalone DB instance |
| **Redis** | 6379 | `6380` | Task broker & PubSub log engine |

---

## 🚀 Remote Server Deployment Guide

### Prerequisites

- **OS:** Debian 11/12, Ubuntu 22.04/24.04, or RHEL/Rocky 9 Linux server.
- **Kernel / Capabilities:** Linux Kernel 5.15+ with loop device support enabled (`modprobe loop`).
- **Software:** `git`, `docker`, and Docker Compose v2 (`docker compose` plugin).

### Step 1: Clone Repository

```bash
git clone https://github.com/masseselsev/edge-duro.git /opt/edge-duro
cd /opt/edge-duro
```

### Step 2: Prepare Host Storage Directory & Permissions

Create the host data directory (e.g. `/data/duro` or `/mnt/nvme/duro_workspace`) and set non-root user permissions so Docker containers and system users can write build artifacts seamlessly:

```bash
# Create directory
sudo mkdir -p /data/duro

# Grant ownership to current non-root user
sudo chown -R $USER:$USER /data/duro

# Set standard write permissions
sudo chmod -R 775 /data/duro
```

### Step 3: Configure Environment Variables & Generate JWT Key

Create the `.env` configuration file:

```bash
cp .env.example .env
nano .env
```

#### Generating a Secure `JWT_SECRET_KEY`

To generate a cryptographically strong 256-bit secret key for JWT session tokens, run either of the following commands:

**Option A (OpenSSL):**
```bash
openssl rand -hex 32
```

**Option B (Python 3):**
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Copy the generated 64-character hexadecimal string into your `.env` file under `JWT_SECRET_KEY`.

#### Production `.env` Example

```env
POSTGRES_USER=postgres
POSTGRES_PASSWORD=SetYourSecureDbPasswordHere
POSTGRES_DB=duro_image_builder
REDIS_URL=redis://redis:6379/0
DATABASE_URL=postgresql://postgres:SetYourSecureDbPasswordHere@db:5432/duro_image_builder

# Exposed Ports
BACKEND_PORT=8003

# Admin Authentication
SUPERADMIN_USERNAME=admin
ADMIN_PASSWORD=SetYourSecureSuperadminPasswordHere
JWT_SECRET_KEY=e8f9a2b4c6d8e0f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f7a9b1c3d5e7f9

# Host Workspace & Build Storage Mount Path
DURO_HOST_DATA_PATH=/data/duro
DURO_WORKSPACE_PATH=/opt/data/duro_workspace
```

### Step 4: Launch Containers

```bash
docker compose up -d --build
```

Verify service health:

```bash
docker compose ps
```

### Step 5: Access Web UI

Navigate to `http://<your-server-ip>:3333` in your web browser.

Default login:
- **Username:** `admin` (or `SUPERADMIN_USERNAME` configured in `.env`)
- **Password:** `q1w2e3r4` (or `ADMIN_PASSWORD` configured in `.env`)

---

## 🔒 Nginx Reverse Proxy & SSL (Optional)

To expose Edge D.U.R.O. securely behind a domain name with SSL/TLS termination:

```nginx
server {
    listen 80;
    server_name duro.your-domain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name duro.your-domain.com;

    ssl_certificate /etc/letsencrypt/live/duro.your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/duro.your-domain.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:3333;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Server-Sent Events (SSE) log streaming support
        proxy_read_timeout 3600s;
        proxy_buffering off;
    }
}
```
