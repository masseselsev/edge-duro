"""
Renaming network interfaces after the prefix given in the recipe.

systemd's predictable names (enp1s0, enx00e04c...) depend on which slot the
card sits in and on its MAC, so two identical boards end up with different
names and a recipe cannot refer to any specific one. A prefix from the recipe
gives the whole fleet the same names: edge0, edge1, edge2.

Numbering starts from the interface the board is actually working through at
install time -- it is almost always the only one plugged in, and it is exactly
the name that has to be known in advance to be written into the configuration.

The name is pinned in two ways at once: with a .link file (for future boots and
for udev) and with a live `ip link set name` on every boot. A .link file alone
is not enough -- on-board NICs get named by udev while still in the initramfs,
where the .link file never ships, and after switch_root systemd-udevd no longer
renames interfaces that already exist.
"""

# The name must not look like something the kernel hands out (eth0, enp1s0):
# systemd refuses to rename an interface into a name from its own namespace.
DEFAULT_PREFIX = "edge"
DEFAULT_START_INDEX = 0

LINK_DIR = "/etc/systemd/network"

# The "names are pinned" stamp. A separate file rather than the presence of a
# .link: a boot without a single active port writes no .link at all and has to
# run again later.
STAMP_PATH = "/var/lib/edge/netnames.done"


def rename_script(prefix: str = DEFAULT_PREFIX, start_index: int = DEFAULT_START_INDEX) -> str:
    """
    The part of firstboot.sh that pins one name per physical interface.

    Matching is done on the MAC, not on the current kernel name: the name can
    change between boots, the MAC cannot, so a single naming pass holds forever.
    The live rename below, in contrast, has to run on every boot.
    """
    return f"""
# --- Network interface naming ------------------------------------------------
edge_rename_interfaces() {{
  local prefix="{prefix}"
  local idx={start_index}
  local link_dir="{LINK_DIR}"
  local stamp="{STAMP_PATH}"
  local active="" iface mac path

  # Names are already pinned -- a second pass would hand out different numbers
  # if another cable got plugged in meanwhile. The guard is the stamp itself,
  # not the presence of .link files: without an active port the pass writes
  # none at all and must run again on the next boot.
  [ -e "$stamp" ] && return 0
  mkdir -p "$link_dir"

  # Virtual interfaces (bridge, veth, lo) have no /sys/class/net/*/device entry.
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

  # With no active port there is no way to tell which interface should come
  # first. Handing names out alphabetically would pin them forever and almost
  # certainly to the wrong socket: the first name would land on a port nobody
  # ever plugged into. Write nothing and leave no stamp -- the check repeats on
  # the next boot and on cable hotplug.
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

# A .link file alone is not enough. On-board NICs (r8169 on the PCIe bus on
# RK3588) show up while still in the initramfs, which never carries our /etc --
# initramfs-tools does not ship /etc/systemd/network/*.link at all. udev inside
# the initramfs names them by its own policy (enP4p65s0), and after switch_root
# systemd-udevd no longer renames interfaces that already exist: net_setup_link
# acts on "add", a later "change" leaves the name alone. So the .link file is
# silently too late forever, and the live name has to be forced by hand -- on
# every boot, until it matches what we want.
edge_apply_live_names() {{
  local link_dir="{LINK_DIR}"
  local f want mac cur iface

  for f in "$link_dir"/10-edge-*.link; do
    [ -e "$f" ] || continue
    want="$(sed -n 's/^Name=//p' "$f" | head -1)"
    mac="$(sed -n 's/^MACAddress=//p' "$f" | head -1)"
    [ -n "$want" ] && [ -n "$mac" ] || continue

    # Look the device up by MAC, not by name: the name is the very thing we
    # are about to change.
    cur=""
    for iface in $(ls /sys/class/net); do
      [ -e "/sys/class/net/$iface/device" ] || continue
      if [ "$(cat "/sys/class/net/$iface/address" 2>/dev/null)" = "$mac" ]; then
        cur="$iface"
        break
      fi
    done
    [ -n "$cur" ] || continue
    [ "$cur" = "$want" ] && continue

    # The kernel refuses to rename an interface that is up (EBUSY), hence the
    # strict down -> name -> up order. The link drops for a fraction of a
    # second; .network files match on the MAC (see edge-netconf.sh) rather than
    # on the name, so they survive the rename without losing the address.
    ip link set dev "$cur" down 2>/dev/null || true
    if ip link set dev "$cur" name "$want" 2>/dev/null; then
      echo "[NETNAME] $cur -> $want (live)"
    else
      echo "[NETNAME] WARNING: could not rename $cur -> $want"
    fi
    ip link set dev "$want" up 2>/dev/null || true
  done
}}

# Deciding who is who happens once (guarded by the stamp), but forcing the live
# name has to repeat on every boot: the kernel hands its own names back after
# each start.
edge_rename_interfaces
edge_apply_live_names
"""
