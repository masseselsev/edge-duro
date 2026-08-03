#!/bin/sh
# Celery worker entrypoint.
#
# Registers a binfmt_misc handler for foreign architectures before starting the
# worker, so mkosi can build arm64 images on an amd64 host. Without it dpkg
# dies on the first maintainer script it has to execute:
#
#   dpkg (subprocess): unable to execute new libc6:arm64 package
#   pre-installation script (...): Exec format error
#
# binfmt_misc is kernel-global rather than per-container, so a handler another
# tool already installed (docker run --privileged tonistiigi/binfmt, or the
# host distribution) is left alone. Registration needs privileged: true, which
# the worker service already has for systemd-nspawn.

set -e

BINFMT_DIR=/proc/sys/fs/binfmt_misc

register_qemu() {
    arch_name="$1"
    interpreter="$2"
    magic="$3"
    mask="$4"

    [ -x "$interpreter" ] || {
        echo "[binfmt] $interpreter missing, skipping $arch_name"
        return 0
    }
    [ -e "$BINFMT_DIR/$arch_name" ] && {
        echo "[binfmt] $arch_name already registered"
        return 0
    }

    # Flags: O keeps the interpreter open at registration time and F preloads
    # it into the kernel, so it stays reachable inside the chroot mkosi builds
    # -- the target rootfs contains no qemu. C applies the binary's credentials.
    if printf ":%s:M::%b:%b:%s:OCF" "$arch_name" "$magic" "$mask" "$interpreter" \
        > "$BINFMT_DIR/register" 2>/dev/null; then
        echo "[binfmt] registered $arch_name -> $interpreter"
    else
        echo "[binfmt] WARNING: could not register $arch_name; foreign-architecture builds will fail"
    fi
}

if [ ! -e "$BINFMT_DIR/register" ]; then
    mount -t binfmt_misc binfmt_misc "$BINFMT_DIR" 2>/dev/null \
        || echo "[binfmt] WARNING: binfmt_misc is not mounted and could not be mounted"
fi

if [ -e "$BINFMT_DIR/register" ]; then
    register_qemu qemu-aarch64 /usr/bin/qemu-aarch64-static \
        '\x7fELF\x02\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02\x00\xb7\x00' \
        '\xff\xff\xff\xff\xff\xff\xff\x00\xff\xff\xff\xff\xff\xff\xff\xff\xfe\xff\xff\xff'
fi

exec "$@"
