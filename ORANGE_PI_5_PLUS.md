# Orange Pi 5 Plus (Rockchip RK3588) — Hardware & System Reference

This document serves as the project memory artifact and technical specification for the **Orange Pi 5 Plus (4GB/8GB/16GB/32GB)** single-board computer, extracted and structured from the official documentation wiki ([Orange Pi 5 Plus Wiki](http://www.orangepi.org/orangepiwiki/index.php/Orange_Pi_5_Plus)).

---

## 1. Hardware Specifications

| Component | Technical Specification |
| :--- | :--- |
| **SoC** | Rockchip RK3588 (Samsung 8nm LP process) |
| **CPU** | Octa-core 64-bit: 4x Cortex-A76 (up to 2.4 GHz) + 4x Cortex-A55 (up to 1.8 GHz), independent NEON coprocessor |
| **GPU** | ARM Mali-G610 MP4 (OpenGL ES 1.1/2.0/3.2, OpenCL 2.2, Vulkan 1.1/1.2), 2D/3D graphics engine |
| **NPU** | 6 TOPS neural network accelerator (supports INT4 / INT8 / INT16 / FP16) |
| **PMU** | Rockchip RK806-1 |
| **RAM** | 4GB / 8GB / 16GB / 32GB LPDDR4 / LPDDR4x |
| **SPI Flash** | 16 MB / 32 MB QSPI NOR Flash onboard (Macronix/Winbond) |
| **Storage Expansion** | • MicroSD (TF) slot (Class 10 / UHS-I)<br>• eMMC socket (supports 32GB / 64GB / 128GB / 256GB modules)<br>• M.2 2280 M-Key slot (PCIe 3.0 x4 for NVMe SSD) |
| **Networking** | 2x 2.5 Gbps Ethernet RJ45 ports (Realtek RTL8125BG controller) |
| **Wi-Fi / Bluetooth** | M.2 2230 E-Key slot (PCIe 2.0 x1 + USB 2.0 for Wi-Fi 6 / Bluetooth 5.2 modules) |
| **Video Outputs** | • 2x HDMI 2.1 Out (up to 8K@60fps or 4K@120fps)<br>• 1x USB Type-C DisplayPort 1.4a Out (up to 8K@30fps / 4K@60fps)<br>• 1x MIPI DSI 4-lane Out (up to 4K@60fps) |
| **Video Input** | • 1x HDMI 2.0 In (up to 4K@60fps)<br>• 1x MIPI CSI 4-lane / 2x MIPI CSI 2-lane camera interface |
| **Audio** | • 3.5mm Headphone/Mic audio combo jack (ES8388 codec)<br>• Onboard analog microphone<br>• 2-pin 1.25mm Speaker header<br>• HDMI & DP digital audio output |
| **USB Ports** | • 2x USB 3.0 Type-A (HOST)<br>• 2x USB 2.0 Type-A (HOST)<br>• 1x USB 3.0 Type-C (Power Delivery + DP 1.4 + Data) |
| **Power Supply** | **5V @ 4A DC via dedicated Type-C port** *(next to Ethernet ports)*. Fixed 5V input only, no PD negotiation. |
| **Expansion Header** | 40-pin GPIO header (2.54mm pitch) with GPIO, UART, I2C, SPI, CAN, PWM |
| **Debug Port** | Dedicated 3-pin UART header (GND, RX, TX) |
| **Buttons** | MaskROM button, Recovery button, Power button, Reset button |
| **Cooling & RTC** | • 2-pin 1.25mm 5V PWM fan connector<br>• 2-pin 1.25mm RTC battery backup connector |
| **Dimensions & Weight**| 100 mm × 75 mm, ~86.5 g |

---

## 2. Power & Interface Rules

### ⚠️ Power Port vs Data Type-C Port
* **Power Port**: The Type-C port located **directly next to the 2.5G Ethernet ports** is the dedicated 5V/4A power input.
* **Peripheral / DisplayPort Type-C**: The second Type-C port *(near the HDMI ports)* is for USB data, ADB, and DisplayPort 1.4 output. **It cannot supply main system power.**
* **Voltage Requirement**: Requires a clean **fixed 5V (4A recommended)**. Standard USB-PD chargers that require 9V/12V/20V negotiation may default to 5V@1A/2A, which causes kernel crashes or reboot loops under high CPU/GPU/NPU loads.

### 💡 Onboard LEDs
* **Red LED (Power)**: Hardwired to the 5V/3.3V power rails. Lights up solid whenever power is connected.
* **Green LED (Status / Heartbeat)**: Controlled by GPIO / kernel LED triggers (`heartbeat` or `mmc0`). Blinks when U-Boot / Linux kernel is active.

### 🔌 Serial Debug UART Header
* **Location**: 3-pin header beside the 40-pin GPIO block (marked `GND`, `RX`, `TX`).
* **Baud Rate**: **`1,500,000` (1.5 Mbps), 8N1** (Rockchip RK3588 hardware default).
* **Signal Voltage**: **3.3V TTL**.

---

## 3. Storage Hierarchy & Boot Architecture

### Boot Order (Rockchip BootROM Hardcoded Sequence):
1. **SPI NOR Flash** (if bootloader present)
2. **MicroSD / TF Card**
3. **eMMC Module**
4. **USB / MaskROM Recovery Mode** *(if no valid bootable media found)*

### ⚠️ RK3588 Raw Bootloader Offsets
RK3588 BootROM does not boot traditional PC UEFI/MBR filesystems directly. It inspects storage devices for raw Rockchip boot structures at fixed physical LBA sector offsets (512-byte sectors):

| LBA Sector | Byte Offset | Component | Description |
| :--- | :--- | :--- | :--- |
| **Sector 64** | `32 KiB` (`0x8000`) | `idbloader.img` | Rockchip TPL + SPL (DDR initialization + early clock setup) |
| **Sector 16384** | `8 MiB` (`0x800000`)| `u-boot.itb` | U-Boot Proper (FIT image containing U-Boot, ATF/BL31, and DTB) |
| **Sector 32768+**| `16 MiB`+ | Partition Table | GPT Partition Table (First partition starts at or after 16 MB) |

### 🚀 Direct NVMe Booting via SPI NOR Flash
* The RK3588 hardware BootROM **cannot boot directly from PCIe NVMe SSDs**.
* To boot an OS located on an NVMe SSD without a microSD card inserted:
  1. The U-Boot bootloader must be flashed into the onboard **SPI NOR Flash** (`/dev/mtdblock0`).
  2. At power-on, the BootROM reads U-Boot from SPI NOR flash.
  3. U-Boot initializes PCIe 3.0, scans the NVMe SSD (`nvme0n1`), loads the kernel (`vmlinuz`) and initrd (`initrd.img`) via `/boot/extlinux/extlinux.conf`, and boots into the NVMe root filesystem.

---

## 4. 40-Pin GPIO Expansion Header Map

All GPIOs operate at **3.3V logic level**.

```
                           40-PIN HEADER PINOUT
                       +3.3V Power [ 1] [ 2] +5V Power
              (I2C6_SDA) GPIO0_B5  [ 3] [ 4] +5V Power
              (I2C6_SCL) GPIO0_B6  [ 5] [ 6] Ground
              (PWM3_M0)  GPIO0_B7  [ 7] [ 8] GPIO0_D3 (UART2_TX)
                         Ground    [ 9] [10] GPIO0_D4 (UART2_RX)
              (PWM7_M0)  GPIO1_A7  [11] [12] GPIO1_B0 (PWM6_M0)
              (PWM5_M0)  GPIO1_B1  [13] [14] Ground
              (PWM4_M0)  GPIO1_B2  [15] [16] GPIO1_B3 (PWM8_M0)
                       +3.3V Power [17] [18] GPIO1_B4 (PWM9_M0)
             (SPI0_MOSI) GPIO1_B5  [19] [20] Ground
             (SPI0_MISO) GPIO1_B6  [21] [22] GPIO1_B7 (SPI0_CLK)
              (SPI0_CS0) GPIO1_C0  [23] [24] GPIO1_C1 (SPI0_CS1)
                         Ground    [25] [26] GPIO3_B1
              (I2C4_SDA) GPIO3_B2  [27] [28] GPIO3_B3 (I2C4_SCL)
              (CAN1_RX)  GPIO3_B4  [29] [30] Ground
              (CAN1_TX)  GPIO3_B5  [31] [32] GPIO3_B6 (PWM11_M0)
              (PWM12_M0) GPIO3_B7  [33] [34] Ground
             (UART6_TX)  GPIO3_C0  [35] [36] GPIO3_C1 (UART6_RX)
                         GPIO3_C2  [37] [38] GPIO3_C3
                         Ground    [39] [40] GPIO3_C4
```

---

## 5. Software & OS Building in Edge DURO

When building Debian or Ubuntu images for the Orange Pi 5 Plus in Edge DURO:

### Key Recipe Configurations:
* **Distribution**: Must be set to **`Armbian`** *(Armbian provides the board-specific hardware adaptation layer over standard Debian/Ubuntu userland)*.
* **Board**: **`Orange Pi 5 Plus`** (`opi5-plus`).
* **Release**:
  * For Ubuntu userland: **`noble`** (24.04 LTS) or **`jammy`** (22.04 LTS).
  * For Debian userland: **`bookworm`** (Debian 12) or **`trixie`** (Debian 13).
* **Architecture**: **`arm64`**.

### Required Packages:
* Kernel: `linux-image-vendor-rk35xx` (Rockchip BSP 6.1.x kernel with full hardware/NPU/VPU/GPU/Display support).
* DTB: `linux-dtb-vendor-rk35xx` (contains `rockchip/rk3588-orangepi-5-plus.dtb`).
* U-Boot: `linux-u-boot-orangepi5-plus-vendor` (contains board SPL & U-Boot proper binaries).

### U-Boot Configuration (`/boot/extlinux/extlinux.conf`):
```text
LABEL Edge OS
  LINUX /boot/vmlinuz-...
  INITRD /boot/initrd.img-...
  FDT /boot/dtb-.../rockchip/rk3588-orangepi-5-plus.dtb
  APPEND root=LABEL=edgeroot rw quiet loglevel=3 fsck.mode=skip console=tty1 console=ttyS2,1500000
```

### Automated Flashing / Provisioning Workflow:
1. **Partition 00 Gap**: `00-rk3588-loader.conf` reserves the first 16 MB of the raw disk image for U-Boot.
2. **Bootloader Injection**: `write_bootloader_into_image()` writes `idbloader.img` to sector 64 and `u-boot.itb` to sector 16384.
3. **Automated NVMe Clone**: When booting from microSD, `edge-firstboot.service` (`core/rk3588.py`) detects an installed NVMe SSD (`/dev/nvme0n1`), clones the partition layout, writes U-Boot to SPI Flash (`/dev/mtdblock0`), expands the root filesystem, and makes the system standalone.

---

## 6. Official Resources & References
* **Official Wiki**: [http://www.orangepi.org/orangepiwiki/index.php/Orange_Pi_5_Plus](http://www.orangepi.org/orangepiwiki/index.php/Orange_Pi_5_Plus)
* **Downloads & Schematics**: [Orange Pi 5 Plus Support Page](http://www.orangepi.org/html/hardWare/computerAndMicrocontrollers/service-and-support/Orange-Pi-5-plus.html)
* **Linux SDK (orangepi-build)**: [GitHub: orangepi-xunlong/orangepi-build](https://github.com/orangepi-xunlong/orangepi-build)
* **Armbian Build Framework**: [GitHub: armbian/build](https://github.com/armbian/build)
