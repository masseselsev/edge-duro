FROM python:3.13-slim
RUN DEBIAN_FRONTEND=noninteractive apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    gcc libpq-dev curl \
    mkosi systemd-container debootstrap \
    xorriso squashfs-tools mtools dosfstools e2fsprogs \
    grub-efi-amd64-bin grub-pc-bin grub-common \
    ubuntu-keyring debian-archive-keyring \
    busybox-static xz-utils cpio \
    qemu-user-static \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
