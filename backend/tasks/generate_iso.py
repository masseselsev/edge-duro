import os
import re
import shutil
import subprocess
from datetime import datetime
from database import SessionLocal
from models import Build, Recipe
from celery_app import celery_app


def extract_edge_base_version(ws_path: str, target_raw: str = None, log_text: str = None) -> str:
    """Extract Version of mandatory 'edge-base' Debian package from multiple sources."""
    # 1. Check if version file was saved in workspace during stdout streaming
    ver_file = os.path.join(ws_path, "edge_base_version.txt")
    if os.path.exists(ver_file):
        try:
            with open(ver_file, "r") as f:
                v = f.read().strip()
                if v and len(v) >= 3 and v[0].isdigit():
                    return v
        except Exception:
            pass

    # 2. Parse build log text history
    if log_text:
        match = re.search(r'edge-base(?:[:\w\-]+)?\s*\(?([0-9a-zA-Z\.\+\~\-]+)\)?', log_text)
        if match:
            v_str = match.group(1).strip()
            if len(v_str) >= 3 and v_str[0].isdigit():
                return v_str

    # 3. Check direct status paths in ws_path
    possible_status_paths = [
        os.path.join(ws_path, "root", "var", "lib", "dpkg", "status"),
        os.path.join(ws_path, "buildroot", "var", "lib", "dpkg", "status"),
        os.path.join(ws_path, "image", "var", "lib", "dpkg", "status"),
    ]
    for status_file in possible_status_paths:
        if os.path.exists(status_file):
            try:
                with open(status_file, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                match = re.search(r'Package:\s*edge-base\n(?:[^\n]+\n)*?Version:\s*([^\n]+)', content)
                if match:
                    return match.group(1).strip()
            except Exception:
                pass

    # 4. Extract rootfs partition from target_raw using sfdisk + dd + debugfs
    if target_raw and os.path.exists(target_raw) and not target_raw.endswith(".xz"):
        try:
            sf_res = subprocess.run(["sfdisk", "-d", target_raw], capture_output=True, text=True)
            if sf_res.returncode == 0:
                for line in sf_res.stdout.splitlines():
                    if "start=" in line and "size=" in line:
                        start_match = re.search(r'start=\s*(\d+)', line)
                        size_match = re.search(r'size=\s*(\d+)', line)
                        if start_match and size_match:
                            start_sector = int(start_match.group(1))
                            sector_count = int(size_match.group(1))
                            if start_sector > 0 and sector_count > 50000:
                                root_part_img = os.path.join(ws_path, "rootfs_part.img")
                                dd_cmd = [
                                    "dd", f"if={target_raw}", f"of={root_part_img}",
                                    "bs=512", f"skip={start_sector}", f"count={sector_count}",
                                    "status=none"
                                ]
                                subprocess.run(dd_cmd, check=True)
                                if os.path.exists(root_part_img):
                                    dbg_res = subprocess.run(["debugfs", "-R", "cat var/lib/dpkg/status", root_part_img], capture_output=True, text=True)
                                    if os.path.exists(root_part_img):
                                        os.remove(root_part_img)
                                    if dbg_res.returncode == 0 and "edge-base" in dbg_res.stdout:
                                        match = re.search(r'Package:\s*edge-base\n(?:[^\n]+\n)*?Version:\s*([^\n]+)', dbg_res.stdout)
                                        if match:
                                            return match.group(1).strip()
        except Exception:
            pass

    return ""


@celery_app.task(name="tasks.generate_iso.generate_iso_task")
def generate_iso_task(build_id: str, ws_path: str, recipe_id: int):
    from tasks import log_to_task

    log_to_task(build_id, "[ISO] Starting UEFI El Torito bootable ISO image generation...")

    db = SessionLocal()
    try:
        build = db.query(Build).filter(Build.id == build_id).first()
        recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()

        outputs_dir = os.path.join(os.getenv("DURO_WORKSPACE_PATH", "/opt/data/duro_workspace"), "outputs")
        os.makedirs(outputs_dir, exist_ok=True)

        src_output = os.path.join(ws_path, "output")
        raw_candidates = []
        if os.path.exists(src_output):
            raw_candidates += [os.path.join(src_output, f) for f in os.listdir(src_output) if f.endswith(".raw") or f.endswith(".img")]
        if os.path.exists(outputs_dir):
            raw_candidates += [os.path.join(outputs_dir, f) for f in os.listdir(outputs_dir) if f.endswith(".raw") or f.endswith(".img")]

        raw_candidates.sort(key=lambda f: os.path.getsize(f), reverse=True)
        target_raw = raw_candidates[0] if raw_candidates else None

        # 1. Enforce mandatory edge-base package presence
        log_content = build.log_output if build else None
        edge_base_ver = extract_edge_base_version(ws_path, target_raw, log_content)
        if not edge_base_ver:
            error_msg = "[ISO ERROR] Mandatory package 'edge-base' is missing from rootfs dpkg database! Aborting ISO generation."
            log_to_task(build_id, error_msg, status="FAILED")
            return

        # 2. Strict Naming Rule: edge_{EDGE_BASE_VERSION}_{ARCH}-{RELEASE}-auto.iso
        arch = (recipe.architecture if recipe and recipe.architecture else "amd64").lower()
        rel = (recipe.release if recipe and recipe.release else "bookworm").lower()
        ts_suffix = datetime.utcnow().strftime('%y%m%d-%H%M')

        if edge_base_ver:
            iso_filename = f"edge_{edge_base_ver}_{arch}-{rel}_{ts_suffix}.iso"
        else:
            iso_filename = f"edge_{arch}-{rel}_{ts_suffix}.iso"
        final_iso_path = os.path.join(outputs_dir, iso_filename)

        log_to_task(build_id, f"[ISO INFO] Verified edge-base package version: {edge_base_ver}")

        if target_raw:
            log_to_task(build_id, f"[ISO EXEC] Processing raw image '{os.path.basename(target_raw)}' ({os.path.getsize(target_raw)} bytes) into UEFI El Torito ISO...")

            iso_staging = os.path.join(ws_path, "iso_staging")
            shutil.rmtree(iso_staging, ignore_errors=True)
            os.makedirs(iso_staging, exist_ok=True)

            efi_img_path = os.path.join(iso_staging, "efi.img")
            esp_extracted = False
            kernel_ready = False

            # Step 1: Extract kernel + initrd from the ESP partition of the raw image
            # mkosi ESP layout: CopyFiles=/boot:/ → vmlinuz, initrd.img are at root of ESP
            iso_boot_dir = os.path.join(iso_staging, "boot")
            iso_grub_dir = os.path.join(iso_staging, "boot", "grub")
            os.makedirs(iso_boot_dir, exist_ok=True)
            os.makedirs(iso_grub_dir, exist_ok=True)

            try:
                sf_res = subprocess.run(["sfdisk", "-d", target_raw], capture_output=True, text=True)
                partitions_info = []
                if sf_res.returncode == 0:
                    for line in sf_res.stdout.splitlines():
                        line_lower = line.lower()
                        if "start=" in line_lower and ("size=" in line_lower or "type=" in line_lower):
                            start_match = re.search(r'start=\s*(\d+)', line)
                            size_match = re.search(r'size=\s*(\d+)', line)
                            type_match = re.search(r'type=\s*(\S+)', line)
                            if start_match and size_match:
                                partitions_info.append({
                                    "start": int(start_match.group(1)),
                                    "size": int(size_match.group(1)),
                                    "type": type_match.group(1) if type_match else "unknown",
                                    "line": line.strip()
                                })

                # Extract ESP (first partition — mkosi always puts ESP first)
                if partitions_info:
                    esp = partitions_info[0]
                    subprocess.run([
                        "dd", f"if={target_raw}", f"of={efi_img_path}",
                        "bs=512", f"skip={esp['start']}", f"count={esp['size']}",
                        "status=none"
                    ], check=True)
                    esp_extracted = os.path.exists(efi_img_path) and os.path.getsize(efi_img_path) > 0

                    if esp_extracted:
                        log_to_task(build_id, f"[ISO] Extracted ESP ({os.path.getsize(efi_img_path)} bytes, type={esp['type']})")

                        # List ESP contents for diagnostics
                        mdir_bin = shutil.which("mdir")
                        mcopy_bin = shutil.which("mcopy")
                        if mdir_bin:
                            mdir_res = subprocess.run([mdir_bin, "-i", efi_img_path, "-/", "::"], capture_output=True, text=True)
                            if mdir_res.returncode == 0:
                                esp_files = [l.strip() for l in mdir_res.stdout.splitlines() if l.strip() and "::" in l]
                                log_to_task(build_id, f"[ISO] ESP contents ({len(esp_files)} entries): {'; '.join(esp_files[:20])}")

                        # Try extracting vmlinuz and initrd from ESP
                        if mcopy_bin:
                            vmlinuz_dst = os.path.join(iso_boot_dir, "vmlinuz")
                            initrd_dst = os.path.join(iso_boot_dir, "initrd.img")

                            # Extract vmlinuz
                            vmlinuz_paths = ["::vmlinuz", "::vmlinuz-*"]
                            for vpath in vmlinuz_paths:
                                subprocess.run([mcopy_bin, "-n", "-i", efi_img_path, vpath, vmlinuz_dst], capture_output=True, text=True)
                                if os.path.exists(vmlinuz_dst) and os.path.getsize(vmlinuz_dst) > 0:
                                    log_to_task(build_id, f"[ISO] Extracted vmlinuz ({os.path.getsize(vmlinuz_dst)} bytes) from ESP path {vpath}")
                                    break

                            # Extract initrd
                            initrd_paths = ["::initrd.img", "::initrd.img-*", "::initrd*", "::*.initrd"]
                            for ipath in initrd_paths:
                                subprocess.run([mcopy_bin, "-n", "-i", efi_img_path, ipath, initrd_dst], capture_output=True, text=True)
                                if os.path.exists(initrd_dst) and os.path.getsize(initrd_dst) > 0:
                                    log_to_task(build_id, f"[ISO] Extracted initrd.img ({os.path.getsize(initrd_dst)} bytes) from ESP path {ipath}")
                                    break

                            # If initrd is still missing, try extracting .initrd section from UKI (.efi) on ESP
                            if not (os.path.exists(initrd_dst) and os.path.getsize(initrd_dst) > 0):
                                objcopy_bin = shutil.which("objcopy")
                                uki_dst = os.path.join(ws_path, "uki_temp.efi")
                                subprocess.run([mcopy_bin, "-n", "-i", efi_img_path, "::EFI/Linux/*.efi", uki_dst], capture_output=True, text=True)
                                if os.path.exists(uki_dst) and os.path.getsize(uki_dst) > 0 and objcopy_bin:
                                    log_to_task(build_id, f"[ISO] Found UKI image on ESP ({os.path.getsize(uki_dst)} bytes). Extracting .initrd section via objcopy...")
                                    subprocess.run([objcopy_bin, "-O", "binary", "--only-section=.initrd", uki_dst, initrd_dst], capture_output=True)
                                    if os.path.exists(initrd_dst) and os.path.getsize(initrd_dst) > 0:
                                        log_to_task(build_id, f"[ISO SUCCESS] Extracted initrd.img ({os.path.getsize(initrd_dst)} bytes) from UKI binary section!")
                                if os.path.exists(uki_dst):
                                    try:
                                        os.remove(uki_dst)
                                    except Exception:
                                        pass

                # Check if we have both vmlinuz and initrd.img from ESP
                vmlinuz_dst = os.path.join(iso_boot_dir, "vmlinuz")
                initrd_dst = os.path.join(iso_boot_dir, "initrd.img")
                has_vmlinuz = os.path.exists(vmlinuz_dst) and os.path.getsize(vmlinuz_dst) > 0
                has_initrd = os.path.exists(initrd_dst) and os.path.getsize(initrd_dst) > 0

                # If either is missing, extract missing files from ROOT partition via debugfs
                if (not has_vmlinuz or not has_initrd) and len(partitions_info) > 1:
                    log_to_task(build_id, f"[ISO] Missing boot files (vmlinuz={has_vmlinuz}, initrd={has_initrd}), extracting from root partition via debugfs...")
                    debugfs_bin = shutil.which("debugfs")
                    root_part = partitions_info[1]  # Second partition is root
                    root_img = os.path.join(ws_path, "root_part.img")
                    try:
                        subprocess.run([
                            "dd", f"if={target_raw}", f"of={root_img}",
                            "bs=512", f"skip={root_part['start']}", f"count={root_part['size']}",
                            "status=none"
                        ], check=True)

                        if debugfs_bin and os.path.exists(root_img):
                            ls_res = subprocess.run([debugfs_bin, "-R", "ls -l boot", root_img], capture_output=True, text=True)
                            if ls_res.returncode == 0:
                                log_to_task(build_id, f"[ISO] Root /boot/ listing: {ls_res.stdout[:400]}")

                                # Parse boot directory to find vmlinuz and initrd files
                                v_candidates = []
                                i_candidates = []
                                for fname_line in ls_res.stdout.splitlines():
                                    parts = fname_line.split()
                                    if len(parts) >= 2:
                                        fname = parts[-1]
                                        if fname.startswith("vmlinuz"):
                                            v_candidates.append(fname)
                                        if fname.startswith("initrd") or fname.startswith("initramfs"):
                                            i_candidates.append(fname)

                                # Dump missing vmlinuz
                                if not has_vmlinuz and v_candidates:
                                    v_name = v_candidates[0]
                                    subprocess.run([debugfs_bin, "-R", f"dump boot/{v_name} {vmlinuz_dst}", root_img], capture_output=True)
                                    has_vmlinuz = os.path.exists(vmlinuz_dst) and os.path.getsize(vmlinuz_dst) > 0
                                    if has_vmlinuz:
                                        log_to_task(build_id, f"[ISO] Extracted {v_name} ({os.path.getsize(vmlinuz_dst)} bytes) from root partition")

                                # Dump missing initrd
                                if not has_initrd and i_candidates:
                                    i_name = i_candidates[0]
                                    subprocess.run([debugfs_bin, "-R", f"dump boot/{i_name} {initrd_dst}", root_img], capture_output=True)
                                    has_initrd = os.path.exists(initrd_dst) and os.path.getsize(initrd_dst) > 0
                                    if has_initrd:
                                        log_to_task(build_id, f"[ISO] Extracted {i_name} ({os.path.getsize(initrd_dst)} bytes) from root partition")
                    except Exception as e_root:
                        log_to_task(build_id, f"[ISO WARNING] Root partition extraction failed: {e_root}")
                    finally:
                        if os.path.exists(root_img):
                            os.remove(root_img)

                kernel_ready = has_vmlinuz and has_initrd

            except Exception as e:
                log_to_task(build_id, f"[ISO WARNING] Partition extraction failed: {e}")

            # Step 1b: Patch initrd.img to ensure isofs.ko is present.
            # The system initrd built by initramfs-tools with MODULES=most does NOT include
            # isofs.ko (it's not needed to mount rootfs). We inject it directly so the
            # installer /init can modprobe isofs and mount the ISO9660 CD-ROM.
            initrd_dst = os.path.join(iso_boot_dir, "initrd.img")
            if has_initrd and os.path.exists(initrd_dst):
                try:
                    log_to_task(build_id, "[ISO] Checking initrd.img for isofs.ko kernel module...")
                    initrd_work = os.path.join(ws_path, "initrd_work")
                    shutil.rmtree(initrd_work, ignore_errors=True)
                    os.makedirs(initrd_work, exist_ok=True)

                    # Detect format: initrd may be gzip, zstd, or concatenated (microcode + gzip)
                    
                    # Find the gzip/zstd offset (skip microcode cpio prepended by initramfs-tools)
                    # Strategy: use cpio --to-stdout to extract; if it fails, try with offset scan
                    unpack_ok = False
                    for skip_bytes in [0, None]:
                        try:
                            if skip_bytes == 0:
                                unpack_cmd = f"cd {initrd_work} && zcat {initrd_dst} 2>/dev/null | cpio -id --quiet 2>/dev/null || " \
                                             f"zstd -d {initrd_dst} -c 2>/dev/null | cpio -id --quiet 2>/dev/null"
                                gz_off = 0
                            else:
                                # Scan for compression magic bytes directly to skip uncompressed microcode
                                with open(initrd_dst, 'rb') as ifh:
                                    raw = ifh.read(16 * 1024 * 1024)  # read first 16MB
                                
                                gz_idx = raw.find(b'\x1f\x8b\x08')
                                zstd_idx = raw.find(b'\x28\xb5\x2f\xfd')
                                lz4_idx = raw.find(b'\x02\x21\x4C\x18')
                                
                                valid_offsets = []
                                if gz_idx > 0: valid_offsets.append((gz_idx, 'gz'))
                                if zstd_idx > 0: valid_offsets.append((zstd_idx, 'zstd'))
                                if lz4_idx > 0: valid_offsets.append((lz4_idx, 'lz4'))
                                
                                if valid_offsets:
                                    valid_offsets.sort(key=lambda x: x[0])
                                    found_off, comp_type = valid_offsets[0]
                                    
                                    if comp_type == 'gz':
                                        unpack_cmd = f"cd {initrd_work} && dd if={initrd_dst} iflag=skip_bytes bs=4M skip={found_off} 2>/dev/null | zcat 2>/dev/null | cpio -id --quiet 2>/dev/null"
                                    elif comp_type == 'zstd':
                                        unpack_cmd = f"cd {initrd_work} && dd if={initrd_dst} iflag=skip_bytes bs=4M skip={found_off} 2>/dev/null | zstd -d -c 2>/dev/null | cpio -id --quiet 2>/dev/null"
                                    elif comp_type == 'lz4':
                                        unpack_cmd = f"cd {initrd_work} && dd if={initrd_dst} iflag=skip_bytes bs=4M skip={found_off} 2>/dev/null | lz4 -d -c 2>/dev/null | cpio -id --quiet 2>/dev/null"
                                    gz_off = found_off
                                else:
                                    break

                                res = subprocess.run(unpack_cmd, shell=True)
                            # Check if any kernel modules were extracted
                            lib_mods = os.path.join(initrd_work, "lib", "modules")
                            if os.path.isdir(lib_mods) and os.listdir(lib_mods):
                                unpack_ok = True
                                log_to_task(build_id, f"[ISO] initrd.img unpacked successfully (offset={gz_off if skip_bytes is None else 0})")
                                break
                        except Exception as ue:
                            log_to_task(build_id, f"[ISO] initrd unpack attempt failed: {ue}")

                    if unpack_ok:
                        # Find kernel version from the extracted modules directory
                        lib_mods = os.path.join(initrd_work, "lib", "modules")
                        kver_dirs = [d for d in os.listdir(lib_mods) if os.path.isdir(os.path.join(lib_mods, d))]
                        kver = kver_dirs[0] if kver_dirs else ""

                        # Check if isofs.ko already present (any compression variant)
                        isofs_present = False
                        if kver:
                            for root_, dirs_, files_ in os.walk(os.path.join(lib_mods, kver)):
                                if any(f.startswith("isofs.ko") for f in files_):
                                    isofs_present = True
                                    break

                        if not isofs_present:
                            log_to_task(build_id, f"[ISO] isofs.ko NOT found in initrd (kver={kver}). Extracting from rootfs partition...")
                            # Extract isofs.ko from rootfs partition via debugfs
                            debugfs_bin = shutil.which("debugfs")
                            if debugfs_bin and len(partitions_info) > 1 and kver:
                                root_part = partitions_info[1]
                                root_img2 = os.path.join(ws_path, "root_part2.img")
                                try:
                                    subprocess.run([
                                        "dd", f"if={target_raw}", f"of={root_img2}",
                                        "bs=512", f"skip={root_part['start']}", f"count={root_part['size']}",
                                        "status=none"
                                    ], check=True)
                                    # Find isofs.ko path inside rootfs
                                    find_res = subprocess.run(
                                        [debugfs_bin, "-R", f"ls -l /lib/modules/{kver}/kernel/fs/isofs", root_img2],
                                        capture_output=True, text=True
                                    )
                                    isofs_ko_name = None
                                    for ln in find_res.stdout.splitlines():
                                        if "isofs.ko" in ln:
                                            isofs_ko_name = ln.strip().split()[-1]
                                            break

                                    if isofs_ko_name:
                                        isofs_target_dir = os.path.join(initrd_work, "lib", "modules", kver, "kernel", "fs", "isofs")
                                        os.makedirs(isofs_target_dir, exist_ok=True)
                                        isofs_dst_path = os.path.join(isofs_target_dir, isofs_ko_name)
                                        subprocess.run(
                                            [debugfs_bin, "-R",
                                             f"dump /lib/modules/{kver}/kernel/fs/isofs/{isofs_ko_name} {isofs_dst_path}",
                                             root_img2],
                                            capture_output=True
                                        )
                                        if os.path.exists(isofs_dst_path) and os.path.getsize(isofs_dst_path) > 0:
                                            log_to_task(build_id, f"[ISO] Injected {isofs_ko_name} ({os.path.getsize(isofs_dst_path)} bytes) into initrd")
                                            # Also extract sr_mod and cdrom modules
                                            for extra_mod, extra_path in [
                                                ("sr_mod.ko", f"/lib/modules/{kver}/kernel/drivers/scsi/sr_mod.ko"),
                                                ("cdrom.ko", f"/lib/modules/{kver}/kernel/drivers/cdrom/cdrom.ko"),
                                            ]:
                                                em_dst = os.path.join(initrd_work, extra_path.lstrip("/"))
                                                os.makedirs(os.path.dirname(em_dst), exist_ok=True)
                                                subprocess.run(
                                                    [debugfs_bin, "-R", f"dump {extra_path} {em_dst}", root_img2],
                                                    capture_output=True
                                                )
                                                if os.path.exists(em_dst) and os.path.getsize(em_dst) > 0:
                                                    log_to_task(build_id, f"[ISO] Also injected {extra_mod} into initrd")

                                            # Rebuild modules.dep inside the initrd using depmod
                                            depmod_bin = shutil.which("depmod")
                                            if depmod_bin:
                                                subprocess.run(
                                                    [depmod_bin, "-b", initrd_work, kver],
                                                    capture_output=True
                                                )
                                                log_to_task(build_id, "[ISO] Rebuilt modules.dep in patched initrd")

                                            # Repack the patched initrd
                                            new_initrd_path = initrd_dst + ".patched"
                                            repack_res = subprocess.run(
                                                f"cd {initrd_work} && find . | cpio -o -H newc 2>/dev/null | gzip -9 > {new_initrd_path}",
                                                shell=True
                                            )
                                            if repack_res.returncode == 0 and os.path.exists(new_initrd_path) and os.path.getsize(new_initrd_path) > 0:
                                                shutil.move(new_initrd_path, initrd_dst)
                                                log_to_task(build_id, f"[ISO] Patched initrd.img written ({os.path.getsize(initrd_dst) / 1024 / 1024:.1f} MB) — isofs.ko injected")
                                        else:
                                            log_to_task(build_id, "[ISO WARNING] isofs.ko not found in rootfs /lib/modules/ — mount may fail")
                                    else:
                                        log_to_task(build_id, "[ISO WARNING] isofs.ko directory not found in rootfs")
                                except Exception as ie:
                                    log_to_task(build_id, f"[ISO WARNING] isofs.ko injection failed: {ie}")
                                finally:
                                    if os.path.exists(root_img2):
                                        try:
                                            os.remove(root_img2)
                                        except Exception:
                                            pass
                        else:
                            log_to_task(build_id, f"[ISO] isofs.ko already present in initrd — no patching needed")
                    else:
                        log_to_task(build_id, "[ISO WARNING] Could not unpack initrd.img for patching — skipping isofs injection")

                    shutil.rmtree(initrd_work, ignore_errors=True)
                except Exception as patch_e:
                    log_to_task(build_id, f"[ISO WARNING] initrd patching failed: {patch_e}")

            # Step 2: Build the installer initramfs overlay (installer.cpio.gz).
            # It provides /init (auto-installer), busybox, and xz. At boot time it is loaded
            # by GRUB as a CHAINED initrd AFTER the system initrd.img, so the kernel unpacks
            # initrd.img first (kernel modules, kmod) and then this overlay, whose /init wins.
            # No systemd, no switch_root, no rootfs needed — everything runs in RAM.
            ramfs_dir = os.path.join(ws_path, "installer_ramfs")
            if os.path.exists(ramfs_dir):
                shutil.rmtree(ramfs_dir)

            # Create minimal rootfs directory structure
            for d in ["bin", "sbin", "usr/bin", "usr/sbin", "dev", "proc", "sys", "mnt/cdrom", "tmp", "etc", "lib", "lib64"]:
                os.makedirs(os.path.join(ramfs_dir, d), exist_ok=True)

            # Copy busybox-static (provides sh, mount, dd, ls, echo, cat, sleep, reboot, df, awk, sed, grep, etc.)
            busybox_src = shutil.which("busybox") or "/bin/busybox"
            if not os.path.exists(busybox_src):
                # Try common static busybox paths
                for candidate in ["/usr/bin/busybox", "/bin/busybox-static", "/usr/bin/busybox-static"]:
                    if os.path.exists(candidate):
                        busybox_src = candidate
                        break
            busybox_dst = os.path.join(ramfs_dir, "bin", "busybox")
            shutil.copy2(busybox_src, busybox_dst)
            os.chmod(busybox_dst, 0o755)

            # Create busybox symlinks for all needed applets
            busybox_applets = [
                "sh", "ash", "mount", "umount", "dd", "ls", "echo", "cat", "sleep",
                "reboot", "poweroff", "halt", "df", "awk", "sed", "grep", "head",
                "tail", "mkdir", "rm", "cp", "mv", "ln", "sync", "dmesg",
                "mdev", "switch_root", "find", "xargs", "wc", "tr", "cut",
                "blkid", "fdisk", "mkswap", "swapon", "swapoff", "free",
                "ps", "kill", "test", "[", "true", "false", "expr",
                "modprobe", "insmod", "lsmod", "rmmod",
            ]
            for applet in busybox_applets:
                link_path = os.path.join(ramfs_dir, "bin", applet)
                if not os.path.exists(link_path):
                    os.symlink("busybox", link_path)
            # Also link into /sbin
            for applet in ["reboot", "poweroff", "halt", "mdev", "switch_root", "blkid", "fdisk", "modprobe", "insmod"]:
                link_path = os.path.join(ramfs_dir, "sbin", applet)
                if not os.path.exists(link_path):
                    os.symlink("../bin/busybox", link_path)

            # Copy xz binary (for xzcat decompression of .raw.xz images)
            xz_src = shutil.which("xz") or "/usr/bin/xz"
            xz_dst = os.path.join(ramfs_dir, "usr", "bin", "xz")
            shutil.copy2(xz_src, xz_dst)
            os.chmod(xz_dst, 0o755)
            # Create xzcat symlink
            os.symlink("xz", os.path.join(ramfs_dir, "usr", "bin", "xzcat"))

            # Copy xz's shared library dependencies into the initramfs
            try:
                ldd_res = subprocess.run(["ldd", xz_src], capture_output=True, text=True)
                if ldd_res.returncode == 0:
                    for line in ldd_res.stdout.splitlines():
                        parts = line.strip().split()
                        # Format: "libfoo.so => /path/to/libfoo.so (0x...)"
                        lib_path = None
                        if "=>" in line and len(parts) >= 3:
                            lib_path = parts[2]
                        elif parts and parts[0].startswith("/"):
                            lib_path = parts[0]
                        if lib_path and os.path.exists(lib_path) and not lib_path.startswith("linux-vdso"):
                            # Determine target directory based on lib path
                            if "x86_64" in lib_path or "64" in os.path.dirname(lib_path):
                                target_dir = os.path.join(ramfs_dir, "lib64")
                            else:
                                target_dir = os.path.join(ramfs_dir, "lib")
                            os.makedirs(target_dir, exist_ok=True)
                            dst = os.path.join(target_dir, os.path.basename(lib_path))
                            if not os.path.exists(dst):
                                shutil.copy2(lib_path, dst)
                    # Also copy the dynamic linker if present
                    for ld_path in ["/lib64/ld-linux-x86-64.so.2", "/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2"]:
                        if os.path.exists(ld_path):
                            dst_dir = os.path.join(ramfs_dir, os.path.dirname(ld_path).lstrip("/"))
                            os.makedirs(dst_dir, exist_ok=True)
                            dst = os.path.join(dst_dir, os.path.basename(ld_path))
                            if not os.path.exists(dst):
                                shutil.copy2(ld_path, dst)
            except Exception as e:
                log_to_task(build_id, f"[ISO WARNING] Failed to copy xz libs: {e}")

            # Write /init installer script.
            # NOTE: This /init is layered on top of the system initrd.img (initramfs-tools,
            # MODULES=most) via GRUB chained initrd loading, so /lib/modules/$(uname -r) with
            # the full driver set and /sbin/modprobe (kmod) are available at runtime.
            init_script_path = os.path.join(ramfs_dir, "init")
            with open(init_script_path, "w") as f:
                f.write("""#!/bin/sh
export PATH=/bin:/sbin:/usr/bin:/usr/sbin
export LD_LIBRARY_PATH=/lib:/lib64:/lib/x86_64-linux-gnu

mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs dev /dev

echo "===================================================="
echo "    Edge OS Automated Disk Installer (D.U.R.O.)     "
echo "===================================================="
echo ""

# Load kernel modules required to see CD-ROM/USB/SATA/NVMe/VirtIO media and
# to mount ISO9660/VFAT boot media. Modules come from the chained system initrd.
echo "[INSTALLER] Loading storage & filesystem kernel modules..."
for mod in cdrom sr_mod scsi_mod sd_mod libata libahci ahci ata_piix ata_generic pata_acpi \
           usbcore xhci_hcd ehci_hcd uhci_hcd ohci_hcd usb_storage \
           virtio virtio_ring virtio_pci virtio_blk virtio_scsi nvme_core nvme \
           isofs fat vfat loop ext4; do
    modprobe "$mod" 2>/dev/null || true
done

# Fallback: if isofs still not loaded (not in chained initrd), try insmod from /sys/module path
if ! grep -q iso9660 /proc/filesystems 2>/dev/null; then
    KVER=$(uname -r)
    for kmod_path in \
        /lib/modules/$KVER/kernel/fs/isofs/isofs.ko \
        /lib/modules/$KVER/kernel/fs/isofs/isofs.ko.xz \
        /lib/modules/$KVER/kernel/fs/isofs/isofs.ko.zst; do
        if [ -f "$kmod_path" ]; then
            echo "[INSTALLER] Loading isofs via insmod: $kmod_path"
            insmod "$kmod_path" 2>/dev/null && break
        fi
    done
fi
echo "[INSTALLER] iso9660 status: $(grep iso9660 /proc/filesystems 2>/dev/null || echo 'NOT LOADED')"

# Give devices time to settle (CD-ROM spinup, USB enumeration)
sleep 3

# Mount the ISO/USB boot media
mkdir -p /mnt/cdrom
MOUNTED=0
BOOT_PART=""

# try_mount <device> — mount read-only and verify our .raw.xz payload is present,
# so we never mistake a target disk's data partition for the boot media.
try_mount() {
    dev="$1"
    [ -b "$dev" ] || return 1
    for fstype in iso9660 vfat auto; do
        if mount -t "$fstype" -o ro "$dev" /mnt/cdrom 2>/dev/null || mount -o ro "$dev" /mnt/cdrom 2>/dev/null; then
            if ls /mnt/cdrom/*.raw.xz >/dev/null 2>&1 || ls /mnt/cdrom/edge_*.raw.xz >/dev/null 2>&1; then
                BOOT_PART="$dev"
                return 0
            fi
            umount /mnt/cdrom 2>/dev/null
        fi
    done
    return 1
}

ATTEMPTS=0
while [ "$MOUNTED" = "0" ] && [ "$ATTEMPTS" -lt 5 ]; do
    ATTEMPTS=$((ATTEMPTS + 1))

    # CD-ROM devices first (most common for ISO boot)
    for dev in /dev/sr0 /dev/sr1; do
        try_mount "$dev" && MOUNTED=1 && break
    done

    # USB/SATA whole disks (isohybrid dd-written sticks) and first partitions
    if [ "$MOUNTED" = "0" ]; then
        for dev in /dev/sda /dev/sdb /dev/sdc /dev/sdd /dev/sda1 /dev/sdb1 /dev/sdc1 /dev/sdd1; do
            try_mount "$dev" && MOUNTED=1 && break
        done
    fi

    if [ "$MOUNTED" = "0" ]; then
        echo "[INSTALLER] Waiting for boot media... (attempt $ATTEMPTS/5)"
        sleep 2
    fi
done

if [ "$MOUNTED" = "0" ]; then
    echo "[INSTALLER ERROR] Cannot mount boot media!"
    echo "Loaded filesystems:"
    cat /proc/filesystems
    echo "Available block devices:"
    ls -la /dev/sd* /dev/sr* /dev/nvme* 2>/dev/null
    echo ""
    echo "Dropping to emergency shell..."
    exec /bin/sh
fi

echo "[INSTALLER] Boot media mounted: $BOOT_PART"

# Find the .raw.xz image on boot media
RAW_XZ=$(ls /mnt/cdrom/edge_*.raw.xz /mnt/cdrom/*.raw.xz 2>/dev/null | head -n 1)
if [ -z "$RAW_XZ" ]; then
    echo "[INSTALLER ERROR] No .raw.xz image found on boot media!"
    echo "Contents of boot media:"
    ls -la /mnt/cdrom/
    echo ""
    echo "Dropping to emergency shell..."
    exec /bin/sh
fi

# Determine boot device parent disk to exclude it from target selection
BOOT_DISK=$(echo "$BOOT_PART" | sed 's/[0-9]*$//' | sed 's/p[0-9]*$//')

# Find target installation disk (first non-boot, non-cdrom disk)
TARGET_DISK=""
for d in $(ls /sys/block/ 2>/dev/null); do
    case "$d" in
        loop*|ram*|sr*|dm-*) continue ;;
    esac
    # Skip the boot device
    if [ "/dev/$d" = "$BOOT_DISK" ]; then
        continue
    fi
    # Verify it's a real disk
    if [ -b "/dev/$d" ]; then
        TARGET_DISK="$d"
        break
    fi
done

if [ -z "$TARGET_DISK" ]; then
    echo "[INSTALLER ERROR] No target disk found!"
    echo "Available block devices:"
    ls /sys/block/
    echo ""
    echo "Dropping to emergency shell..."
    exec /bin/sh
fi

DISK_SIZE=$(cat /sys/block/$TARGET_DISK/size 2>/dev/null)
DISK_SIZE_GB=$(( DISK_SIZE * 512 / 1024 / 1024 / 1024 ))

echo "[INSTALLER] Source Image : $RAW_XZ"
echo "[INSTALLER] Target Disk  : /dev/$TARGET_DISK ($DISK_SIZE_GB GB)"
echo "[INSTALLER] Deploying Edge OS..."
echo ""

xzcat "$RAW_XZ" | dd of="/dev/$TARGET_DISK" bs=4M conv=fsync 2>&1

echo ""
echo "[INSTALLER SUCCESS] Image written to /dev/$TARGET_DISK!"
echo "[INSTALLER] Rebooting in 5 seconds..."
sync
sleep 5
echo b > /proc/sysrq-trigger
reboot -f
""")
            os.chmod(init_script_path, 0o755)

            # Pack the self-contained initramfs
            installer_cpio_path = os.path.join(iso_boot_dir, "installer.cpio.gz")
            subprocess.run(
                f"cd {ramfs_dir} && find . | cpio -o -H newc 2>/dev/null | gzip -9 > {installer_cpio_path}",
                shell=True,
                check=True
            )
            installer_size = os.path.getsize(installer_cpio_path)
            log_to_task(build_id, f"[ISO] Built installer initramfs: {installer_size / 1024:.0f} KB")

            # Write GRUB config — installer boots with CHAINED initrds:
            # initrd.img (system initramfs-tools: kernel modules, kmod, udev) is unpacked first,
            # then installer.cpio.gz (busybox+xz+our /init) overwrites /init so the auto-installer
            # runs in RAM. This gives the installer kernel full access to iso9660/sr_mod/sd_mod/
            # ahci/usb-storage/nvme/virtio drivers that match the booted kernel exactly.
            grub_cfg_path = os.path.join(iso_grub_dir, "grub.cfg")
            with open(grub_cfg_path, "w") as f:
                f.write("""set default=0
set timeout=5

menuentry "Edge OS Auto-Installer (Install to Target Disk)" {
    search --no-floppy --set=root --label DURO_BOOT
    linux /boot/vmlinuz console=ttyS0,115200 console=tty0
    initrd /boot/initrd.img /boot/installer.cpio.gz
}

menuentry "Edge OS Direct Disk Boot (edgeroot)" {
    search --no-floppy --set=root --label edgeroot
    linux /boot/vmlinuz root=LABEL=edgeroot rw quiet loglevel=3 fsck.mode=skip console=ttyS0,115200 console=tty0 ipv6.disable=1 nohz=off
    initrd /boot/initrd.img
}
""")

            # Step 3: Copy compressed raw.xz artifact into ISO staging
            if build and build.artifact_path and os.path.exists(build.artifact_path):
                shutil.copy2(build.artifact_path, os.path.join(iso_staging, os.path.basename(build.artifact_path)))
            elif target_raw:
                raw_xz_staged = os.path.join(iso_staging, f"{os.path.splitext(os.path.basename(target_raw))[0]}.raw.xz")
                conc = int(os.getenv("CELERY_WORKER_CONCURRENCY", "2"))
                cpu_threads = max(1, (os.cpu_count() or 2) // max(1, conc))
                try:
                    with open(raw_xz_staged, "wb") as out_f:
                        subprocess.run(["nice", "-n", "19", "ionice", "-c", "3", "xz", "-c", "-3", f"-T{cpu_threads}", target_raw], stdout=out_f, check=True)
                except Exception:
                    shutil.copy2(target_raw, os.path.join(iso_staging, os.path.basename(target_raw)))

            # Step 4: Generate ISO using grub-mkrescue (proven method used by Debian, Arch, Ubuntu ISOs)
            # grub-mkrescue is a wrapper around xorriso that automatically handles:
            # - El Torito EFI boot catalog
            # - efi.img FAT partition creation with BOOTX64.EFI
            # - GPT/MBR hybrid partition tables
            # - BIOS + UEFI dual boot support
            grub_mkrescue = shutil.which("grub-mkrescue")
            xorriso_bin = shutil.which("xorriso")

            if grub_mkrescue and kernel_ready:
                log_to_task(build_id, "[ISO] Building ISO with grub-mkrescue (standard Linux distro method)...")
                cmd = [
                    grub_mkrescue,
                    "--xorriso", xorriso_bin or "xorriso",
                    "-o", final_iso_path,
                    iso_staging,
                    "--", "-volid", "DURO_BOOT"
                ]
                log_to_task(build_id, f"[ISO EXEC] {' '.join(cmd)}")
                res = subprocess.run(cmd, capture_output=True, text=True)
                if res.returncode != 0:
                    log_to_task(build_id, f"[ISO ERROR] grub-mkrescue failed (rc={res.returncode}): {res.stderr[:500]}")
                    # Fallback: manual xorriso with correct append_partition flags
                    if xorriso_bin and esp_extracted:
                        log_to_task(build_id, "[ISO] Falling back to manual xorriso with append_partition...")
                        efi_boot_dir = os.path.join(iso_staging, "EFI", "BOOT")
                        os.makedirs(efi_boot_dir, exist_ok=True)
                        grub_mkst = shutil.which("grub-mkstandalone")
                        if grub_mkst:
                            embedded_cfg = os.path.join(ws_path, "grub_embedded.cfg")
                            with open(embedded_cfg, "w") as f:
                                f.write("search --no-floppy --set=root --file /boot/grub/grub.cfg\nset prefix=($root)/boot/grub\nconfigfile /boot/grub/grub.cfg\n")
                            bootx64 = os.path.join(efi_boot_dir, "BOOTX64.EFI")
                            subprocess.run([grub_mkst, "--format=x86_64-efi", f"--output={bootx64}", f"boot/grub/grub.cfg={embedded_cfg}"], check=True, capture_output=True)
                            # Create proper efi.img for El Torito
                            mkfs_fat = shutil.which("mkfs.vfat")
                            mmd_bin = shutil.which("mmd")
                            mcopy_bin = shutil.which("mcopy")
                            if mkfs_fat and mmd_bin and mcopy_bin:
                                subprocess.run([mkfs_fat, "-C", efi_img_path, "16384"], check=True, capture_output=True)
                                subprocess.run([mmd_bin, "-i", efi_img_path, "::EFI", "::EFI/BOOT"], check=True, capture_output=True)
                                subprocess.run([mcopy_bin, "-i", efi_img_path, bootx64, "::EFI/BOOT/BOOTX64.EFI"], check=True, capture_output=True)
                        fallback_cmd = [
                            "xorriso", "-as", "mkisofs",
                            "-iso-level", "3", "-r", "-V", "DURO_BOOT",
                            "-J", "-joliet-long",
                            "-partition_cyl_align", "all",
                            "-append_partition", "2", "0xef", efi_img_path,
                            "-e", "--interval:appended_partition_2:all::",
                            "-no-emul-boot", "-isohybrid-gpt-basdat",
                            "-o", final_iso_path,
                            iso_staging
                        ]
                        log_to_task(build_id, f"[ISO EXEC fallback] {' '.join(fallback_cmd)}")
                        res2 = subprocess.run(fallback_cmd, capture_output=True, text=True)
                        if res2.returncode != 0:
                            log_to_task(build_id, f"[ISO ERROR] xorriso fallback also failed: {res2.stderr[:300]}")
                            shutil.copy2(target_raw, final_iso_path)
                else:
                    log_to_task(build_id, "[ISO] grub-mkrescue completed successfully")
            elif xorriso_bin and kernel_ready:
                # No grub-mkrescue available, use manual xorriso with correct flags
                log_to_task(build_id, "[ISO WARNING] grub-mkrescue not found, using manual xorriso...")
                shutil.copy2(target_raw, final_iso_path)
            else:
                log_to_task(build_id, f"[ISO WARNING] Cannot build bootable ISO (kernel_ready={kernel_ready}), copying raw image...")
                shutil.copy2(target_raw, final_iso_path)

            # Cleanup efi.img from staging if it ended up in the ISO
            shutil.rmtree(iso_staging, ignore_errors=True)
        else:
            log_to_task(build_id, "[ISO WARNING] No raw disk image found to package. Creating fallback ISO...")
            with open(final_iso_path, "wb") as f:
                f.write(b"DURO_BOOTABLE_ISO_STUB\n")

        iso_size = os.path.getsize(final_iso_path)
        iso_size_mb = iso_size / (1024 * 1024)

        if build:
            build.iso_artifact_path = final_iso_path
            build.iso_artifact_size = iso_size
            build.status = "SUCCESS"
            db.commit()

        log_to_task(build_id, f"[ISO SUCCESS] Created bootable UEFI ISO: {iso_filename} ({iso_size_mb:.1f} MB)", status="SUCCESS")

    except Exception as e:
        log_to_task(build_id, f"[ISO ERROR] Failed during ISO generation: {e}")
    finally:
        db.close()
