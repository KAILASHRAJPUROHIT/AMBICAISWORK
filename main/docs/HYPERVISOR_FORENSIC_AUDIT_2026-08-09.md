# Hypervisor / system-freeze forensic audit — 2026-08-09

## Finding

The recurrent fatal-error family is an Intel platform/firmware CrashLog path interacting with the Windows hypervisor surface. FLUX.2 Klein did not create it. Klein and heavy desktop load can expose the system to more stress, but the same firmware records existed weeks before Klein was installed.

Exact driver/module attribution is unavailable because every minidump referenced by Windows Event 1001 has since been removed from `C:\Windows\Minidump`. `C:\Windows\MEMORY.DMP`, LiveKernelReports and WER crash archives are also empty.

## Evidence

- Machine: HP OMEN Slim Gaming Laptop 16-an0xxx / 16-an0012TX, Core Ultra 9 285H, 32 GB RAM, RTX 5070 Laptop 8 GB, Intel Arc 140T.
- BIOS: AMI F.13, dated 2026-01-21. Whether HP has a newer BIOS could not be proven from HP's JavaScript driver portal during this audit.
- Windows: build 26200.8875, 25H2.
- VBS is running. Memory Integrity/HVCI and Hyper-V services are enabled.
- Confirmed `0x00020001 HYPERVISOR_ERROR` crashes: 2026-08-03 20:39, 2026-08-05 17:50, 2026-08-06 17:46, 2026-08-06 20:58.
- Later unclean freezes with fatal WHEA records but no saved bugcheck: 2026-08-08 09:57 and 11:13.
- Separate failures: `0x116 VIDEO_TDR_FAILURE` on 2026-06-28 and `0x12c EXFAT_FILE_SYSTEM` on 2026-06-29.
- Twelve fatal WHEA Event 1 CPER records span 2026-06-15 through 2026-08-08.
- Every WHEA record has six `WHEA_FIRMWARE_ERROR_RECORD_REFERENCE` sections (`81212a96-09ed-4996-9471-8d729c8e69ed`). Their record identifier is `8f87f311-c998-4d9e-a0c4-6065518c4f6d`, the Intel CrashLog GUID.
- This signature predates Klein, Kaspersky's 2026-07-29 installation, and NVIDIA 610.88's 2026-08-06 installation. None can be the root cause of the recurring family.
- Two monitors were active during this audit. RTX free VRAM was 6,977 MB. Displays alone are not exhausting VRAM.
- Unsafe live memory condition was present: 5.69 GB physical RAM free, 82% memory load, 40.85/61.63 GB commit, about 7,885 pages/sec. Catalogue `app.py` held 8.73 GB private memory. This explains application/desktop freezing during long Klein runs, but not the earlier Intel firmware WHEA records.

## Cause ranking

1. Intel Arrow Lake-H platform firmware/microcode/power-state interaction with Hyper-V/VBS/HVCI.
2. Platform hardware instability (CPU/SoC/RAM/mainboard). Still possible; not proven without HP diagnostics and an A/B run.
3. Separate NVIDIA/display TDR issue. Proven once, but it does not explain the Intel firmware CPER family.
4. Klein-induced RAM/VRAM paging. Proven cause of severe apparent hangs; trigger/load amplifier only, not root cause of `0x20001`.
5. Kaspersky/current NVIDIA driver. Ruled out as the original cause by dates.

## Changes made

- Klein now fails closed before a prompt when RAM, commit or VRAM headroom is unsafe.
- A running prompt is interrupted if memory reaches a machine-stall emergency threshold.
- Prompt deadline reduced from 30 minutes to 8 minutes. Timeout actively interrupts and removes the owned prompt.
- Dashboard Stop now interrupts the owned ComfyUI prompt instead of only cancelling the Python wrapper.
- Launcher retains `--cache-none --disable-dynamic-vram --lowvram`; adds disabled previews and disabled auto-launch.
- Five hidden Copilot account profiles were found running despite local-only lockdown. Root cause: `app.py` unconditionally warmed every account at startup. Warm-up is now restricted to actual cloud mode. The launcher also starts no cloud or Comfy editor Chrome by default. Cloud profiles require `ARADHANA_START_CLOUD_BROWSERS=1`; the Comfy editor requires `ARADHANA_OPEN_COMFY_MONITOR=1`.
- Chrome is assigned to the integrated GPU. Comfy Python is assigned to the high-performance GPU.
- The broken nested-`cmd.exe` launcher was replaced by `launch_catalog_ui.ps1`; `LAUNCH_CATALOG_UI.bat` remains the stable double-click entry point.
- A copy-only crash-dump archiver exists. Standard-user access to `C:\Windows\Minidump` is denied on this machine, so reliable automatic preservation requires the included administrator-only scheduled-task installer.

## Activation verification

- Capture remained healthy on unchanged PID 22944 throughout activation.
- Both displays remained active: Intel 1920x1080 and NVIDIA 2560x1440.
- Catalogue private memory after restart: 546 MB, down from 8.73 GB.
- Free physical RAM after restart: 13.54 GB, up from 5.69 GB.
- Hidden cloud browser listeners after restart: zero.
- Klein admission snapshot: allowed; 13.55 GB RAM free, 46.7% commit, 7.01 GB CUDA VRAM free.
- Isolated smoke generation completed in 62.6 seconds with pixel-hash match and shadow-check pass. Production capture, processing and output files were not modified.
- Post-smoke: Comfy queue empty, 13.63 GB RAM free, 6.61 GB RTX VRAM free, capture healthy.
- Test suite: 511 passed, 0 failed.

## Remaining proof test requiring reboot and explicit approval

Run a controlled VBS/Hyper-V A/B period after confirming HP BIOS, Intel ME/chipset and graphics packages are current. Disabling VBS/HVCI reduces security and can break WSL/Docker/virtual machines, so it was not done automatically. If crashes stop with VBS disabled, firmware/hypervisor interaction is confirmed. If Intel CrashLog WHEA events continue, run HP UEFI extensive CPU and memory tests and escalate as platform hardware/firmware.

## 2026-08-10 safety revision

Two further WHEA/hypervisor crashes coincided with local Klein generation.
The live Comfy log showed Flux fully offloaded (`0.00 MB loaded`, 4,209 MB
offloaded) and 12,860 MB pinned host memory. The launcher no longer uses
`--lowvram --disable-dynamic-vram`. It now enforces
`--enable-dynamic-vram --disable-async-offload --disable-pinned-memory` and
refuses an existing Comfy process whose command line cannot be verified.
Preflight/runtime RAM and commit limits were also tightened. This reduces the
known load amplifier; it does not prove or repair the underlying Intel
firmware/hypervisor failure.
