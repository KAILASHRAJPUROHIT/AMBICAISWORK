# CaptureCam E2E timing — 2026-08-25 — LOCKET 22

Observed live from Android logcat. Times are local (`Asia/Calcutta`).

## Timing

| Milestone | Timestamp | Elapsed from first tag |
|---|---:|---:|
| First valid tag read | 18:23:50.820 | 0.000 s |
| Second confirming tag read | 18:23:51.145 | 0.325 s |
| Category resolved and JEWEL phase entered (`locket_22`) | 18:23:53.417 | 2.597 s |
| Stable category ROI locked | 18:24:05.515 | 14.695 s |
| First full-resolution original downloaded (`DSC01491.JPG`) | 18:24:56.484 | 65.664 s |
| Second original downloaded (`DSC01492.JPG`) | 18:25:12.549 | 81.729 s |
| Third original downloaded (`DSC01493.JPG`) | 18:25:22.233 | 91.413 s |
| Fourth original downloaded (`DSC01494.JPG`) | 18:25:37.513 | 106.693 s |
| Last original downloaded (`DSC01495.JPG`) | 18:25:45.507 | **114.687 s** |
| Lens fully wide (0%) | 18:25:51.078 | 120.258 s |
| TAG focus area restored; ready for next item | 18:25:51.087 | **120.267 s** |

First tag appearance to last physical full-resolution image: **1 min 54.687 s**.

First tag appearance to next-tag-ready state: **2 min 0.267 s**.

## Findings

- Tag detection itself was fast: two valid reads were 325 ms apart; JEWEL phase began after 2.597 s.
- Largest delay was jewellery framing: stable ROI lock to first original took 50.969 s. Repeated centering, zoom and hold cycles dominated this period.
- Five full-resolution Sony originals were downloaded although the target set is three views. Files were `DSC01491.JPG` through `DSC01495.JPG`. Manual zoom interaction also occurred, so logs cannot distinguish automatic duplicate shutters from operator retakes without explicit per-view capture sequence IDs.
- Each 17–18 MB full-resolution transfer took about 4.8–5.5 s total. Download alone took about 3.7–4.3 s.
- Post-capture wide reset worked: 1800 ms WIDE command, reported zoom changed/held at 0%, and TAG focus area was restored.
- During the measured capture cycle, live view was approximately 25 FPS with zero stream reopens. Latest-only dropping prevented a growing preview backlog while still files downloaded.

## Next instrumentation required

Log a unique set ID, view (`MAIN`, `ANGLE_1`, `ANGLE_2`), attempt number, shutter request ID, Sony filename, preview decision (`CONTINUE`/`RETAKE`), and acceptance timestamp. This will prove whether the two extra originals are duplicate automatic shutters or intentional retakes.
