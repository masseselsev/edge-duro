"""
Провижининг RK3588-плат (Orange Pi 5 Plus) с многоразовой microSD.

Одна и та же карта проходит по всем платам подряд: на каждой она клонирует
себя на NVMe, кладёт загрузчик в SPI и делает клон уникальным. Поэтому
признак "уже сделано" хранится на цели, а не на карте -- иначе карта
отработала бы ровно один раз.

Загрузчик пишется скриптом самого Armbian (/usr/lib/u-boot/platform_install.sh
из linux-u-boot-orangepi5-plus-vendor): смещения idbloader.img/u-boot.itb и
выбор rkspi_loader.img -- его забота, дублировать их здесь значит однажды
разойтись с апстримом.
"""

import os

MARKER_PATH = "/var/opt/edge/.edge-provisioned"

UBOOT_PLATFORM_SCRIPT = "/usr/lib/u-boot/platform_install.sh"


def provision_script(marker_path: str = MARKER_PATH) -> str:
    """
    Кусок firstboot.sh: клонирование на NVMe, загрузчик в SPI, индивидуализация.

    Запускается на каждой загрузке -- на уже провижиненной плате выходит на
    проверке маркера.
    """
    return f"""
# --- RK3588 (Orange Pi 5 Plus): клонирование на NVMe -------------------------
edge_rk3588_provision() {{
  local target="/dev/nvme0n1"
  local marker="{marker_path}"
  local mnt="/run/edge-provision"

  if [ ! -b "$target" ]; then
    echo "[PROVISION] $target отсутствует -- пропуск."
    return 0
  fi

  # Носитель, с которого мы сейчас загружены, трогать нельзя ни при каких
  # обстоятельствах: перепутать его с целью -- значит затереть себя на ходу.
  local root_src boot_disk
  root_src="$(findmnt -no SOURCE / 2>/dev/null || true)"
  boot_disk="$(lsblk -no PKNAME "$root_src" 2>/dev/null | head -1 || true)"
  if [ -z "$boot_disk" ]; then
    echo "[PROVISION] Не удалось определить носитель, с которого загружены -- отказ."
    return 0
  fi
  if [ "/dev/$boot_disk" = "$target" ]; then
    echo "[PROVISION] Загружены с $target -- провижининг не нужен."
    return 0
  fi

  # Диск меньше карты оборвал бы dd на середине и оставил цель с обрубленной
  # таблицей разделов -- то есть небезопасно загружаемой.
  local src_size tgt_size
  src_size="$(blockdev --getsize64 "/dev/$boot_disk" 2>/dev/null || echo 0)"
  tgt_size="$(blockdev --getsize64 "$target" 2>/dev/null || echo 0)"
  if [ "$tgt_size" -lt "$src_size" ]; then
    echo "[PROVISION] $target ($tgt_size Б) меньше карты ($src_size Б) -- отказ."
    return 0
  fi

  # Маркер лежит на цели, а не на карте: карта переезжает на следующую плату.
  mkdir -p "$mnt"
  local part
  for part in $(lsblk -lno NAME "$target" | tail -n +2); do
    if mount "/dev/$part" "$mnt" 2>/dev/null; then
      if [ -f "$mnt$marker" ]; then
        umount "$mnt"
        echo "[PROVISION] $target уже провижинен."
        return 0
      fi
      umount "$mnt"
    fi
  done

  echo "[PROVISION] Клонирование $boot_disk -> $target ..."
  sync
  dd if="/dev/$boot_disk" of="$target" bs=4M conv=fsync status=progress
  sync
  partprobe "$target" 2>/dev/null || true
  udevadm settle 2>/dev/null || true

  # Копия снята с смонтированной ФС, поэтому журнал на клоне заведомо грязный.
  for part in $(lsblk -lno NAME "$target" | tail -n +2); do
    e2fsck -fy "/dev/$part" >/dev/null 2>&1 || true
  done

  # Карта маленькая, диск большой -- без растягивания последний раздел
  # останется размером с карту.
  local last_num
  last_num="$(lsblk -lno NAME "$target" | tail -n +2 | tail -1 | sed 's/.*[^0-9]//')"
  if [ -n "$last_num" ]; then
    growpart "$target" "$last_num" >/dev/null 2>&1 || true
    resize2fs "${{target}}p${{last_num}}" >/dev/null 2>&1 || true
  fi

  edge_rk3588_write_spi
  edge_rk3588_individualize "$target" "$mnt" "$marker"

  echo "[PROVISION] Готово. NVMe загрузочен, карту можно переставлять."
}}

# Плата не умеет стартовать с NVMe сама: boot ROM читает только SPI/eMMC/SD.
# Загрузчик в SPI -- это то, что позволяет вынуть карту насовсем.
edge_rk3588_write_spi() {{
  local script="{UBOOT_PLATFORM_SCRIPT}"
  if [ ! -f "$script" ]; then
    echo "[PROVISION] $script не найден -- SPI пропущен, карту вынимать нельзя."
    return 0
  fi
  if [ ! -e /dev/mtdblock0 ]; then
    echo "[PROVISION] SPI (/dev/mtdblock0) не найден -- пропуск."
    return 0
  fi

  # shellcheck source=/dev/null
  . "$script"
  echo "[PROVISION] Запись загрузчика в SPI ..."
  write_uboot_platform_mtd "$DIR" /dev/mtdblock0
  sync
}}

# Клон обязан отличаться от оригинала до того, как впервые загрузится:
# одинаковые machine-id и ключи SSH на всём парке -- это поломанный DHCP-lease
# и бессмысленная проверка подлинности хоста.
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
    echo "[PROVISION] Корневой раздел на $target не найден -- индивидуализация пропущена."
    return 0
  fi

  : > "$mnt/etc/machine-id"
  rm -f "$mnt/var/lib/dbus/machine-id"
  rm -f "$mnt"/etc/ssh/ssh_host_*key "$mnt"/etc/ssh/ssh_host_*key.pub

  # Ключи генерируются здесь, а не на первой загрузке клона: так плата
  # поднимается с рабочим SSH сразу, без ещё одного цикла перезагрузки.
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
    Делает собранный RAW загрузочным для BootROM RK3588.

    Без этого шага образ корректен как файловая система, но плата с него не
    стартует: в начале носителя нет ни idbloader, ни u-boot. А без стартующей
    SD не запустится и firstboot, который прошивает SPI -- то есть замкнутый
    круг, где провижининг не может начаться.

    Сами смещения берутся из write_uboot_platform() Armbian, лежащего внутри
    собранного образа: они зависят от платы и версии загрузчика, и своя копия
    однажды разошлась бы с апстримом.
    """
    import json
    import shutil
    import subprocess
    import tempfile

    def _run(cmd, **kw):
        return subprocess.run(cmd, capture_output=True, text=True, **kw)

    probe = _run(["sfdisk", "-J", raw_path])
    if probe.returncode != 0:
        log(f"[RK3588] Не читается таблица разделов: {probe.stderr.strip()}")
        return False

    root_start = None
    for part in json.loads(probe.stdout)["partitiontable"]["partitions"]:
        if part.get("name") == "edgeroot":
            root_start = part["start"]
            break
    if root_start is None:
        log("[RK3588] В образе нет раздела edgeroot -- загрузчик записать не из чего.")
        return False

    mnt = tempfile.mkdtemp(prefix="rk3588-root-")
    staging = tempfile.mkdtemp(prefix="rk3588-uboot-")
    try:
        mount = _run(["mount", "-o", f"ro,loop,offset={root_start * 512}", raw_path, mnt])
        if mount.returncode != 0:
            log(f"[RK3588] Не смонтировать корневой раздел: {mount.stderr.strip()}")
            return False

        try:
            script_src = os.path.join(mnt, UBOOT_PLATFORM_SCRIPT.lstrip("/"))
            if not os.path.exists(script_src):
                log(f"[RK3588] В образе нет {UBOOT_PLATFORM_SCRIPT} -- пакет U-Boot платы не установлен.")
                return False

            # DIR= внутри скрипта указывает на каталог с бинарниками загрузчика;
            # имя каталога зависит от платы, поэтому берётся из самого скрипта.
            uboot_dir = None
            for line in open(script_src):
                if line.startswith("DIR="):
                    uboot_dir = line.split("=", 1)[1].strip()
                    break
            if not uboot_dir:
                log("[RK3588] В platform_install.sh нет DIR= -- не найти бинарники загрузчика.")
                return False

            src_dir = os.path.join(mnt, uboot_dir.lstrip("/"))
            if not os.path.isdir(src_dir):
                log(f"[RK3588] Каталог загрузчика {uboot_dir} отсутствует в образе.")
                return False

            shutil.copy2(script_src, os.path.join(staging, "platform_install.sh"))
            payload = os.path.join(staging, "uboot")
            shutil.copytree(src_dir, payload)
        finally:
            _run(["umount", mnt])

        # Скрипт на bash: [[ ]] и функции dash не осилит.
        written = _run([
            "bash", "-c",
            'set -e; source "$1"; write_uboot_platform "$2" "$3"',
            "_", os.path.join(staging, "platform_install.sh"), payload, raw_path,
        ])
        if written.returncode != 0:
            log(f"[RK3588] write_uboot_platform не отработал: {(written.stderr or written.stdout).strip()}")
            return False

        log("[RK3588] Загрузчик записан в образ штатным скриптом Armbian -- образ загрузочный.")
        return True
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(mnt, ignore_errors=True)
