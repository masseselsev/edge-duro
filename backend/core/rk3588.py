"""
Provisioning RK3588 boards (Orange Pi 5 Plus) from a reusable microSD card.

One and the same card goes through every board in turn: on each one it clones
itself onto the NVMe, puts the bootloader into SPI and makes the clone unique.
That is why the "already done" mark is kept on the target rather than on the
card -- otherwise the card would work exactly once.

The bootloader is written by Armbian's own script
(/usr/lib/u-boot/platform_install.sh from linux-u-boot-orangepi5-plus-vendor):
the idbloader.img/u-boot.itb offsets and the choice of rkspi_loader.img are its
business, and duplicating them here would mean drifting from upstream one day.
"""

import os

# The marker has to live on the clone's ROOT filesystem. /var/opt/edge is a
# partition of its own (LABEL=edgestor), so writing there through the mounted
# root landed inside the mount-point directory: on a running system edgestor is
# mounted over it and the marker became invisible (`cat` returned "No such file
# or directory" even though the file was present in the image). /var/lib is
# never a separate partition -- netnames.done, growfs.done and netconf.done all
# live there too.
MARKER_PATH = "/var/lib/edge/.edge-provisioned"

UBOOT_PLATFORM_SCRIPT = "/usr/lib/u-boot/platform_install.sh"


def provision_script(marker_path: str = MARKER_PATH) -> str:
    """
    The part of firstboot.sh that clones onto NVMe, writes the bootloader into
    SPI and individualizes the clone.

    Runs on every boot -- on a board booted from the target it returns at the
    boot-device check.
    """
    return f"""
# --- RK3588 (Orange Pi 5 Plus): cloning onto NVMe ----------------------------
edge_rk3588_provision() {{
  local target="/dev/nvme0n1"
  local marker="{marker_path}"
  local mnt="/run/edge-provision"

  if [ ! -b "$target" ]; then
    echo "[PROVISION] $target not present -- skipping."
    return 0
  fi

  # The medium we are currently booted from must never be touched under any
  # circumstances: mistaking it for the target means wiping ourselves midway.
  local root_src boot_disk
  root_src="$(findmnt -no SOURCE / 2>/dev/null || true)"
  boot_disk="$(lsblk -no PKNAME "$root_src" 2>/dev/null | head -1 || true)"
  if [ -z "$boot_disk" ]; then
    echo "[PROVISION] Could not determine the boot device -- aborting."
    return 0
  fi
  if [ "/dev/$boot_disk" = "$target" ]; then
    echo "[PROVISION] Already booted from $target -- provisioning not needed."
    return 0
  fi

  # The card is a transit medium and is often many times larger than the
  # partitions actually in use. Copying it whole would push tens of needless
  # gigabytes and demand an NVMe no smaller than the card; copying up to the end
  # of the last partition is enough. A dd cut short midway would leave the
  # target with a truncated partition table, i.e. not safely bootable -- which
  # is why a target smaller than the payload is rejected.
  local last_end payload_bytes tgt_size
  last_end="$(partx -g -o END "/dev/$boot_disk" 2>/dev/null | tail -1 | tr -d ' ')"
  if [ -z "$last_end" ]; then
    echo "[PROVISION] Could not read the partition table of /dev/$boot_disk -- aborting."
    return 0
  fi
  payload_bytes=$(( (last_end + 1) * 512 ))
  tgt_size="$(blockdev --getsize64 "$target" 2>/dev/null || echo 0)"
  if [ "$tgt_size" -lt "$payload_bytes" ]; then
    echo "[PROVISION] $target ($tgt_size B) is smaller than the data ($payload_bytes B) -- aborting."
    return 0
  fi

  # Provisioning is unconditional: while debugging, the target is rewritten
  # every time an NVMe is visible in the system, even one already written. The
  # marker still goes onto the target -- it is the record that the clone was
  # completed and verified. Once debugging is over a condition will come back
  # here (the plan is a jumper between pins 39 and 40, GND and GPIO3_C4).
  mkdir -p "$mnt"
  local part

  echo "[PROVISION] Cloning $boot_disk -> $target ($payload_bytes B) ..."
  sync
  dd if="/dev/$boot_disk" of="$target" bs=4M count=$(( (payload_bytes + 4194303) / 4194304 )) \
     conv=fsync status=progress
  sync

  # The copy stops at the end of the last partition, while the backup GPT
  # header sat at the very end of the card -- on the target it is missing
  # entirely until it is rebuilt from the primary header.
  if ! sfdisk --relocate gpt-bak-std "$target" >/dev/null 2>&1; then
    echo "[PROVISION] WARNING: could not rebuild the backup GPT on $target."
  fi

  partprobe "$target" 2>/dev/null || true
  udevadm settle 2>/dev/null || true

  # The copy was taken from a mounted filesystem, so the clone's journal is
  # dirty by definition.
  for part in $(lsblk -lno NAME "$target" | tail -n +2); do
    e2fsck -fy "/dev/$part" >/dev/null 2>&1 || true
  done

  # The last partition arrived image-sized -- stretch it over the full capacity
  # of the disk. This is the only place the clone is grown: it happens offline,
  # on a target that is not mounted yet, which is why armbian ships no separate
  # edge-growfs unit. As of Ubuntu 24.04 sfdisk lives in a package of its own,
  # "fdisk" (split out of util-linux) -- it is in _REQUIRED_PACKAGES/packages.py,
  # but the reminder stays here in case someone tries to drop it from there as
  # "not obviously needed". growpart lives in cloud-guest-utils, which is not in
  # the image's package list at all, so calling it did nothing, silently.
  local last_part last_num last_label last_fstype
  last_part="$(lsblk -nrpo NAME,TYPE "$target" 2>/dev/null | awk '$2=="part" {{p=$1}} END {{print p}}')"
  last_num="$(echo "$last_part" | grep -o '[0-9]*$')"
  if [ -n "$last_num" ]; then
    last_label="$(blkid -o value -s LABEL "$last_part" 2>/dev/null)"
    last_fstype="$(blkid -o value -s TYPE "$last_part" 2>/dev/null)"
    echo ", +" | sfdisk -N "$last_num" --no-reread --force "$target" >/dev/null 2>&1 || true
    partx -u "$target" >/dev/null 2>&1 || partprobe "$target" >/dev/null 2>&1 || true
    udevadm settle >/dev/null 2>&1 || true

    # resize2fs cannot grow this far: it went from ~32 MiB to ~930 GiB, roughly
    # 29000x, and mkfs reserves only a bounded number of group-descriptor blocks
    # for future online growth -- nowhere near that ratio. On real hardware this
    # produced "Corrupt group descriptor: bad block for block bitmap" and a
    # corrupt journal superblock, caught by e2fsck -fn right after provisioning.
    # The partition is provably empty at this point (just cloned, nothing but
    # lost+found), so recreating the filesystem at its final size is both safe
    # and the only approach whose group-descriptor table is sized correctly for
    # that size from the start.
    if [ "$last_fstype" = "ext4" ]; then
      if [ -n "$last_label" ]; then
        mkfs.ext4 -q -F -L "$last_label" "$last_part" >/dev/null 2>&1 || true
      else
        mkfs.ext4 -q -F "$last_part" >/dev/null 2>&1 || true
      fi
    else
      e2fsck -fy "$last_part" >/dev/null 2>&1 || true
      resize2fs "$last_part" >/dev/null 2>&1 || true
    fi
  fi

  # A truncated copy would leave the board with SPI flashed but no root: the
  # kernel starts and drops into the initramfs with "LABEL=edgeroot does not
  # exist", while the provisioning marker would claim everything was done.
  # Better to stop here, leaving the card bootable and the target plainly
  # unprovisioned -- the next boot will try again.
  udevadm settle 2>/dev/null || true
  if ! blkid -t LABEL=edgeroot "$target"* >/dev/null 2>&1; then
    echo "[PROVISION] Clone incomplete: no edgeroot filesystem on $target -- SPI and marker left untouched."
    edge_rk3588_announce "NVMe provisioning FAILED -- clone incomplete, card left bootable"
    return 0
  fi

  edge_rk3588_write_spi
  edge_rk3588_individualize "$target" "$mnt" "$marker"

  # Interface names are bound to this board's MACs and would match nothing on
  # the next one -- its interfaces would simply keep their kernel names. The
  # clone is already taken and kept its own names, while the card leaves clean
  # and will name the ports again from scratch.
  #
  # Nothing grows the card's partitions: armbian ships no edge-growfs unit at
  # all (see workspace.py), and what was grown above was the target, not the
  # card. The card stays image-sized and moves to the next board as it is.
  rm -f /etc/systemd/network/10-edge-*.link
  rm -f /var/lib/edge/netnames.done

  edge_rk3588_led_done
  edge_rk3588_announce "NVMe provisioned OK -- remove the card and reboot"
  echo "[PROVISION] Done. NVMe is bootable, the card can be moved to the next board."
}}

# The LED is only visible if somebody is looking at the board. The same result
# goes in words to where a human will actually read it: the active console
# (HDMI -- tty1, serial -- console) and /etc/issue, so the line stays above the
# login prompt even after the boot output has scrolled past.
edge_rk3588_announce() {{
  local msg="$1" dev
  for dev in /dev/tty1 /dev/console; do
    [ -w "$dev" ] && printf '\\n*** %s ***\\n\\n' "$msg" > "$dev" 2>/dev/null || true
  done
  # Our own line is rewritten rather than accumulated: while debugging,
  # provisioning repeats on every boot.
  if [ -f /etc/issue ]; then
    sed -i '/^\\[EDGE\\]/d' /etc/issue 2>/dev/null || true
    printf '[EDGE] %s\\n' "$msg" >> /etc/issue
  fi
}}

# The board's only controllable LED is the green one: the red is wired straight
# to the power rail and lights up from the mere fact of voltage being applied.
# The directory name under /sys/class/leds comes from the device tree and
# differs between kernels, so the first suitable one is taken rather than a
# hardcoded name. A steady blink once a second is the "clone written and
# verified" signal, visible without a serial console.
edge_rk3588_led_done() {{
  local led
  for led in /sys/class/leds/*status* /sys/class/leds/*green* /sys/class/leds/*; do
    [ -d "$led" ] || continue
    [ -w "$led/trigger" ] || continue
    echo timer > "$led/trigger" 2>/dev/null || continue
    echo 500 > "$led/delay_on" 2>/dev/null || true
    echo 500 > "$led/delay_off" 2>/dev/null || true
    echo "[PROVISION] Completion signalled on LED $(basename "$led")."
    return 0
  done
  echo "[PROVISION] No writable LED found -- completion not signalled."
}}

# The board cannot start from NVMe on its own: the boot ROM only reads
# SPI/eMMC/SD. The bootloader in SPI is what makes it possible to remove the
# card for good.
edge_rk3588_write_spi() {{
  local script="{UBOOT_PLATFORM_SCRIPT}"
  if [ ! -f "$script" ]; then
    echo "[PROVISION] $script not found -- SPI flashing skipped, do not remove the card."
    return 0
  fi
  if [ ! -e /dev/mtdblock0 ] && [ ! -e /dev/mtd0 ]; then
    echo "[PROVISION] SPI (/dev/mtd0) not found -- skipping."
    return 0
  fi

  # shellcheck source=/dev/null
  . "$script"
  echo "[PROVISION] Writing bootloader to SPI ..."
  # Armbian's own write_uboot_platform_mtd() writes rkspi_loader.img via
  # plain "dd ... of=/dev/mtdblock0" -- the block-device compatibility
  # layer, which was timed at 4+ minutes for this 16 MB image on real
  # hardware (single erase-block-sized cache, no native MTD ioctls).
  # flashcp writes the exact same bytes to the exact same chip through
  # /dev/mtd0's native MEMERASE/MEMWRITE ioctls instead, which is
  # dramatically faster -- this changes only the write mechanism, not any
  # bootloader offset, so it does not touch the "don't reimplement
  # Armbian's own layout knowledge" boundary this function otherwise keeps.
  # Falls back to Armbian's own function if flashcp or the image is missing.
  local spi_img="$DIR/rkspi_loader.img"
  if [ -f "$spi_img" ] && [ -e /dev/mtd0 ] && command -v flashcp >/dev/null 2>&1; then
    flashcp -v -p "$spi_img" /dev/mtd0
  else
    write_uboot_platform_mtd "$DIR" /dev/mtdblock0
  fi
  sync
}}

# The clone has to differ from the original before it ever boots: identical
# machine-ids and SSH keys across the fleet mean broken DHCP leases and a
# meaningless host authenticity check.
edge_rk3588_individualize() {{
  local target="$1" mnt="$2" marker="$3"
  local rootpart=""
  local part

  for part in $(lsblk -lno NAME "$target" | tail -n +2); do
    if mount "/dev/$part" "$mnt" 2>/dev/null; then
      if [ -d "$mnt/etc" ] && [ -d "$mnt/var" ]; then
        rootpart="/dev/$part"
        break
      fi
      umount "$mnt"
    fi
  done

  if [ -z "$rootpart" ]; then
    echo "[PROVISION] Root partition not found on $target -- individualization skipped."
    return 0
  fi

  : > "$mnt/etc/machine-id"
  rm -f "$mnt/var/lib/dbus/machine-id"
  rm -f "$mnt"/etc/ssh/ssh_host_*key "$mnt"/etc/ssh/ssh_host_*key.pub

  # Keys are generated here rather than on the clone's first boot: that way the
  # board comes up with working SSH straight away, without another reboot
  # cycle.
  ssh-keygen -A -f "$mnt" >/dev/null 2>&1 || true

  mkdir -p "$(dirname "$mnt$marker")"
  date -u +"%Y-%m-%dT%H:%M:%SZ" > "$mnt$marker"

  sync
  umount "$mnt"
}}

edge_rk3588_provision
"""


def write_bootloader_into_image(raw_path: str, log=print) -> bool:
    """
    Makes the built RAW image bootable for the RK3588 BootROM.

    Without this step the image is a perfectly valid filesystem, but the board
    will not start from it: there is neither idbloader nor u-boot at the start
    of the medium. And without an SD that starts, firstboot -- the thing that
    flashes SPI -- never runs either: a closed loop in which provisioning can
    never begin.

    The offsets themselves come from Armbian's write_uboot_platform(), which
    lives inside the built image: they depend on the board and on the bootloader
    version, and a copy of our own would drift from upstream one day.
    """
    import json
    import shutil
    import subprocess
    import tempfile

    def _run(cmd, **kw):
        return subprocess.run(cmd, capture_output=True, text=True, **kw)

    probe = _run(["sfdisk", "-J", raw_path])
    if probe.returncode != 0:
        log(f"[RK3588] Could not read the partition table: {probe.stderr.strip()}")
        return False

    root_start = None
    for part in json.loads(probe.stdout)["partitiontable"]["partitions"]:
        if part.get("name") == "edgeroot":
            root_start = part["start"]
            break
    if root_start is None:
        log("[RK3588] Image has no edgeroot partition -- nothing to write the bootloader from.")
        return False

    mnt = tempfile.mkdtemp(prefix="rk3588-root-")
    staging = tempfile.mkdtemp(prefix="rk3588-uboot-")
    try:
        mount = _run(["mount", "-o", f"ro,loop,offset={root_start * 512}", raw_path, mnt])
        if mount.returncode != 0:
            log(f"[RK3588] Could not mount the root partition: {mount.stderr.strip()}")
            return False

        try:
            script_src = os.path.join(mnt, UBOOT_PLATFORM_SCRIPT.lstrip("/"))
            if not os.path.exists(script_src):
                log(f"[RK3588] Image has no {UBOOT_PLATFORM_SCRIPT} -- the board's U-Boot package is not installed.")
                return False

            # DIR= inside the script points at the directory holding the
            # bootloader binaries; the directory name depends on the board, so
            # it is taken from the script itself.
            uboot_dir = None
            for line in open(script_src):
                if line.startswith("DIR="):
                    uboot_dir = line.split("=", 1)[1].strip()
                    break
            if not uboot_dir:
                log("[RK3588] platform_install.sh has no DIR= -- cannot locate the bootloader binaries.")
                return False

            src_dir = os.path.join(mnt, uboot_dir.lstrip("/"))
            if not os.path.isdir(src_dir):
                log(f"[RK3588] Bootloader directory {uboot_dir} is missing from the image.")
                return False

            shutil.copy2(script_src, os.path.join(staging, "platform_install.sh"))
            payload = os.path.join(staging, "uboot")
            shutil.copytree(src_dir, payload)
        finally:
            _run(["umount", mnt])

        # The script is bash: dash cannot handle its [[ ]] and functions.
        written = _run([
            "bash", "-c",
            'set -e; source "$1"; write_uboot_platform "$2" "$3"',
            "_", os.path.join(staging, "platform_install.sh"), payload, raw_path,
        ])
        if written.returncode != 0:
            log(f"[RK3588] write_uboot_platform failed: {(written.stderr or written.stdout).strip()}")
            return False

        log("[RK3588] Bootloader written into the image via Armbian's own script -- image is bootable.")
        return True
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(mnt, ignore_errors=True)
