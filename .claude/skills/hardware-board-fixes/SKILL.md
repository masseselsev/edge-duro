---
name: hardware-board-fixes
description: Use when adding a fix, firmware, kernel module, or workaround for one specific board's hardware (RK3588 or otherwise) in this repo -- covers where in the build/postinst pipeline to gate it and how to keep it from silently shipping to boards that don't need it.
---

# Hardware Board Fixes

## Overview

A fix for one board's silicon has no business running on a different board,
even one sharing the same SoC family. `is_armbian(recipe.distribution)` or
`architecture == "arm64"` selects *every* ARM board -- gate on the specific
board instead.

**Real case:** the Orange Pi 5 Plus's on-board 2.5GbE NICs need
`rtl_nic/rtl8125b-2.fw`; without it `r8169` still links up, just degraded
("Unable to load firmware", caught live on hardware). The fix -- fetching
that one file -- was gated on `board_key(recipe.board) == "opi5-plus"`, not
on `is_armbian()`, because a different RK3588 board (e.g. NanoPC-T6 LTS) may
not even carry that NIC. It was first implemented as an apt-get inside
`mkosi.postinst` (Ubuntu ships the file only inside the ~655 MB
`linux-firmware` package) and had to be abandoned: the chroot has no `gpgv`
(auth failures), and even after fixing that, a 655 MB fetch over this
network hit a mirror connection reset mid-download. It now fetches the 3 KB
file directly from its upstream project at *prepare* time, in Python, with a
persistent cross-build cache -- see `_BOARD_FIRMWARE` / `_fetch_firmware_file`
in `core/workspace.py`. `rockchip/dptx.bin` (the DisplayPort controller behind
the board's USB-C outputs) rides the same table.

## When to Use

- Adding a kernel module, firmware blob, DTB overlay, U-Boot variant, or udev
  rule that a *specific* board's hardware needs.
- Symptom in a boot log or `dmesg` names a specific chip/driver ("Unable to
  load firmware", "invalid resource", a missing `/sys/class/...` node) rather
  than something generic to the SoC or distro.

**Not for:** anything true of the whole SoC family or of Armbian generally
(e.g. the RK3588 console baud rate, U-Boot's own boot chain) -- those stay
gated on `is_armbian()` as before.

## Pattern

```python
# core/packages.py: board_key() lowercases and defaults to "generic" -- always
# route through it, never compare recipe.board directly (case, None-safety).
from core.packages import board_key, is_armbian

some_board_fix_block = ""
if is_armbian(recipe.distribution) and board_key(getattr(recipe, "board", None)) == "opi5-plus":
    some_board_fix_block = """
    ...the fix, as a postinst/firstboot shell fragment...
"""
```

Then interpolate `{some_board_fix_block}` into the f-string that builds
`postinst_script` or `firstboot_lines` in `core/workspace.py` -- same
convention as `extlinux_block` and `virtio_iso_modules_block` there.

## Registering a New Board

1. Add the board's key to `BOARDS` in `frontend/src/components/BoardSelector.tsx`
   with `ready: false` until the backend mappings below actually exist --
   a selectable-but-unwired board silently ships a non-booting image.
2. Wire `ARMBIAN_KERNEL_PACKAGES`, `ARMBIAN_BOARD_PACKAGES`, `ARMBIAN_BOARD_DTB`,
   `ARMBIAN_BOARD_CONSOLE` in `core/packages.py` for the new key.
3. Only then flip `ready: true`.

## Common Mistakes

| Mistake | Why it bites |
|---|---|
| Gating on `is_armbian()` alone | Ships the fix to every RK3588 board, including ones without that chip |
| Comparing `recipe.board == "opi5-plus"` directly | Skips `board_key()`'s lowercasing/None-default, breaks on case or missing board |
| Listing a board in the UI before its backend mappings exist | Produces a selectable option that silently builds a non-booting image |
| Installing a whole firmware/driver package for one file | Check size first (`Installed-Size` in the repo's `Packages` index) -- `linux-firmware` is ~655 MB download for one ~3 KB blob. If the file has a stable upstream home (kernel.org/gitlab.com project, not just a distro package), fetch it directly instead of through apt -- add it to `_BOARD_FIRMWARE` in `core/workspace.py` |
| Fetching a build-time asset from inside `mkosi.postinst`'s chroot | That chroot has no `gpgv`, so any apt operation fails authentication unless you add `--allow-insecure-repositories`/`--allow-unauthenticated` everywhere; a plain HTTPS fetch from Python at *prepare* time (before the chroot exists at all) sidesteps this entirely |
| Trusting an HTTP 200 as proof the download is right | Some hosts (e.g. `git.kernel.org`) serve an HTML challenge/error page with a 200 status depending on `User-Agent`; validate the content itself (e.g. a known binary header) before writing it into the image |
| Ignoring `W: Possible missing firmware ... for built-in driver X` from update-initramfs | Each line names a driver compiled into the board's kernel that will fail to initialise its hardware. Check whether the driver matters for the board (`rockchipdrm` and `cfg80211` do; DVB tuner blobs on a board with no tuner do not) before dismissing it |
| `mount --bind /dev` into a build chroot | mkosi's sandbox builds the `/dev` it hands to scripts as a **tmpfs of empty regular files** with the real device nodes bind-mounted on top, one per node (`DevOperation` in `mkosi/sandbox.py`). A non-recursive bind copies only the tmpfs, so `$ROOT/dev/null` becomes a 0-byte root-owned regular file. apt then runs `apt-key` as `_apt`, its `>/dev/null` redirect dies with `Permission denied`, and apt reports `gpgv ... required for verification, but neither seems installed` **while gpgv is installed**. Always `mount --rbind` (and `umount -R -l`) |
| Assuming a package is present because apt pulled it in as a dependency | `ca-certificates` was never in `_REQUIRED_PACKAGES`, so every in-chroot HTTPS fetch failed with "No system certificates available" -- including `apt.armbian.com`, which redirects to an HTTPS mirror. The board shipped unable to see kernel updates, and nothing in the build failed |
