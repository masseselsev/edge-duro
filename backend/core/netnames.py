"""
Переименование сетевых интерфейсов по префиксу из рецепта.

Предсказуемые имена systemd (enp1s0, enx00e04c...) зависят от того, в какой
слот воткнута карта и какой у неё MAC, поэтому на двух одинаковых платах они
разные, и рецепт не может ссылаться на конкретное имя. Префикс из рецепта даёт
одинаковые имена на всём парке: edge0, edge1, edge2.

Нумерация начинается с интерфейса, через который плата работает в момент
установки -- он почти всегда единственный подключённый, и именно его имя нужно
знать заранее, чтобы прописать в конфигурацию.
"""

# Имя должно быть непохоже на то, что раздаёт ядро (eth0, enp1s0): systemd
# отказывается переименовывать интерфейс в имя из своего же пространства.
DEFAULT_PREFIX = "edge"
DEFAULT_START_INDEX = 0

LINK_DIR = "/etc/systemd/network"

# Метка "имена закреплены". Отдельный файл, а не наличие .link: загрузка без
# единого активного порта не пишет .link вовсе и обязана повториться позже.
STAMP_PATH = "/var/lib/edge/netnames.done"


def rename_script(prefix: str = DEFAULT_PREFIX, start_index: int = DEFAULT_START_INDEX) -> str:
    """
    Кусок firstboot.sh, создающий по .link-файлу на каждый физический интерфейс.

    Привязка идёт к MAC, а не к текущему имени ядра: имя может меняться между
    загрузками, MAC -- нет, поэтому одного прохода достаточно навсегда.
    """
    return f"""
# --- Именование сетевых интерфейсов -----------------------------------------
edge_rename_interfaces() {{
  local prefix="{prefix}"
  local idx={start_index}
  local link_dir="{LINK_DIR}"
  local stamp="{STAMP_PATH}"
  local active="" iface mac path

  # Имена уже закреплены -- второй проход выдал бы другие номера, если к плате
  # успели подключить ещё один кабель. Признак -- именно метка, а не наличие
  # .link-файлов: без активного порта проход не пишет их вовсе и обязан
  # повториться на следующей загрузке.
  [ -e "$stamp" ] && return 0
  mkdir -p "$link_dir"

  # Виртуальные интерфейсы (bridge, veth, lo) не имеют записи в /sys/class/net/*/device.
  for iface in $(ls /sys/class/net); do
    [ -e "/sys/class/net/$iface/device" ] || continue
    if [ "$(cat "/sys/class/net/$iface/carrier" 2>/dev/null)" = "1" ]; then
      active="$iface"
      break
    fi
  done

  edge_write_link() {{
    local dev="$1" name="$2"
    mac="$(cat "/sys/class/net/$dev/address" 2>/dev/null)"
    [ -n "$mac" ] || return 0
    path="$link_dir/10-edge-$name.link"
    printf '[Match]\\nMACAddress=%s\\n\\n[Link]\\nName=%s\\n' "$mac" "$name" > "$path"
    echo "[NETNAME] $dev ($mac) -> $name"
  }}

  # Без активного порта неизвестно, какой интерфейс должен стать первым.
  # Раздать имена по алфавиту -- значит закрепить их навсегда и почти наверняка
  # не тем разъёмом: первое имя уехало бы на порт, в который никто не включался.
  # Ничего не пишем и не ставим метку -- проверка повторится на следующей
  # загрузке и при горячем подключении кабеля.
  if [ -z "$active" ]; then
    echo "[NETNAME] no port has a link yet -- naming deferred until one is connected."
    return 0
  fi

  edge_write_link "$active" "$prefix$idx"
  idx=$((idx + 1))

  for iface in $(ls /sys/class/net); do
    [ -e "/sys/class/net/$iface/device" ] || continue
    [ "$iface" = "$active" ] && continue
    edge_write_link "$iface" "$prefix$idx"
    idx=$((idx + 1))
  done

  mkdir -p "$(dirname "$stamp")"
  : > "$stamp"
}}

edge_rename_interfaces
"""
