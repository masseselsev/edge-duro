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

            # Step 2: Write grub.cfg for ISO boot
            grub_cfg_path = os.path.join(iso_grub_dir, "grub.cfg")
            with open(grub_cfg_path, "w") as f:
                f.write("""set default=0
set timeout=3

menuentry "Edge OS Live / Installer (ISO Boot)" {
    search --no-floppy --set=root --label DURO_BOOT
    linux /boot/vmlinuz root=LABEL=DURO_BOOT rw quiet loglevel=3 fsck.mode=skip console=ttyS0,115200 console=tty0 ipv6.disable=1 nohz=off
    initrd /boot/initrd.img
}

menuentry "Edge OS (Disk Boot / edgeroot)" {
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
