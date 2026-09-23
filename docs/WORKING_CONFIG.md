# Working configuration — safety revision 2026-08-10

> **Superseded safety note:** the 2026-08-08 low-VRAM configuration below
> completed a batch, but later logs showed a 4,209 MB full model offload and
> 12,860 MB pinned-host allocation during recurrent WHEA/hypervisor crashes.
> It must not be restored. The launcher now enforces dynamic VRAM with async
> offload and pinned memory disabled.

The setup below produced a full 65-item jhumka run with **zero generation
failures**. Every number here was measured on this machine, not assumed.
If runs start crawling again, check this file before changing code.

---

## The one thing that matters most

**Klein must get a FULL model load.** A partial load is not a slowdown, it is
a cliff:

```
loaded completely   ->   2.11 s/it   (prompt done in ~33s)
loaded partially    -> 159.79 s/it   (260 MB offloaded)
```

A **75-100x** collapse for being ~260 MB short. ComfyUI commits to that
decision for the whole prompt, so once it happens the item costs ~10 minutes.

Check before a batch:

```bash
nvidia-smi --query-gpu=memory.free --format=csv,noheader
```

Flux2 needs **4,209 MiB**. Want **> 4,500 MiB free**. Below that, expect
partial loads.

Confirm during a run — this line is the ground truth:

```bash
grep -a "loaded completely\|loaded partially" comfy_boot.err.log | tail -3
```

---

## ComfyUI launch flags (in launch_catalog_ui.ps1)

```
--cache-none --enable-dynamic-vram --disable-async-offload --disable-pinned-memory
```

| Flag | Why |
|---|---|
| `--cache-none` | ComfyUI's RAM cache grew to **14.3 GB** with `--cache-lru 4`, filling system RAM and forcing the machine to page. Bounded at ~4.4 GB with cache off. |
| `--enable-dynamic-vram` | Uses ComfyUI's current bounded-RAM loader instead of the obsolete forced-low-VRAM path. |
| `--disable-async-offload` | Prevents multi-stream weight transfers through large host buffers. Safer; potentially slower. |
| `--disable-pinned-memory` | Prevents the measured 12.86 GB pinned-host reservation. Safer; potentially slower. |

The launcher refuses to reuse a Comfy process unless these flags are verified.
Admission also requires 10 GB free physical RAM, at most 70% memory load and
at most 75% committed memory. No production generation is considered proven
safe until a controlled test completes without a new WHEA event.

---

## Desktop hygiene (the single biggest VRAM factor)

The RTX drives the BenQ over HDMI (HDMI is hard-wired to the dGPU on this
chassis; the USB-C ports have no display output). So desktop compositing
lives in the same 8 GB Klein needs.

Measured free VRAM:

| State | Free |
|---|---|
| BenQ + Chrome (52 procs) + Firefox | 249 MiB — **fails** |
| BenQ + apps closed | 5,612 MiB |
| BenQ unplugged | 7,203 MiB |
| **BenQ + per-app GPU prefs + Chrome quit** | **7,206 MiB — current** |

**Chrome is the dominant consumer, not the monitor.** 52 background processes
survive closing the window. Quit it properly:

```bash
taskkill /IM chrome.exe /F
```

Per-app GPU preferences are set in
`HKCU:\Software\Microsoft\DirectX\UserGpuPreferences` — browsers and desktop
apps to `GpuPreference=1` (Intel Arc), ComfyUI/tool Python to `=2` (NVIDIA).
They apply at process launch, so restart an app after changing it.

**Ollama auto-starts and takes 5.5 GB of RAM.** Disable its startup entry.

---

## Code-side fixes that keep it stable

- **Phase A runs in a subprocess** (`precompute_cli.py`). In-process it grew
  app.py from 47 MB to **8,919 MB** and never returned it — `release_small_models()`
  frees VRAM but cannot return host memory (CPython keeps arenas, torch keeps
  pinned buffers). A child process exiting makes the reclaim absolute.
- **No `release_small_models()` in app.py.** It reached `torch.cuda.mem_get_info()`,
  which initialises a CUDA context in app.py costing 300-600 MB of the VRAM
  we are trying to give Klein. Pointless once Phase A moved out of process.
- **`reclaim_between_items()`** frees ComfyUI's idle reserve after each item
  (measured: 4,416 MB reserved, **1,001 MB unused**). No-ops if the queue is busy.

---

## QA gates

| Gate | Behaviour | Why |
|---|---|---|
| Piece count vs `category_topology` | **blocks** | Unambiguous. Caught JB22_5 shipping 3 earrings for a 2-piece SKU. |
| Pair similarity | **flags only** (0.83) | Insufficient separation: good pairs run 0.836-0.978, the one known defect scored 0.810. Chain-tassel pieces score low because fringes drape differently left/right — the lowest scorers are correct, elaborate pieces. Blocking at 0.87 withheld three flawless items. |
| Crop guard (CLIP) | rejects | Scores each ornament box, not the whole plate. Whole-plate scoring fails on pairs: velvet between two earrings outweighs the gold. |
| Stock variety missing | **publishes + flags** | Variety no longer determines the output path (flat `output/<category>/`). Blocking on it cost 8 of 65 correct images on 2026-08-08. |

---

## Known-good numbers

- ~**47s per item** end to end (generation ~33s + pipeline work)
- **65 items ≈ 50 min** on a clean machine
- Prompt execution **31-40s**, step rate **1.5-2.5 s/it**
- GPU **50-100 W**, **55-68°C** under load

---

## Unresolved

- **HYPERVISOR_ERROR (0x00020001)** — 6 crashes in 3 days. VBS/HVCI +
  Hyper-V (`vmms`) + Kaspersky collision, not failing hardware. Fixes, least
  invasive first: update Kaspersky; stop `vmms` if Hyper-V is not needed;
  disable Memory Integrity as a test; BIOS update from F.13.
- **Stock routing metadata is stale** — `31072026.xls` against inventory
  `02082026.xls` leaves **99 tags** without a variety. A fresh Ornate export
  into `Stock\` clears it.
- **`progress_earrings.json` lost entries across a crash** (46 recorded vs 57
  published). Resume is less reliable than the output folder itself.
