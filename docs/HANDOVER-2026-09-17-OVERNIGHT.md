# Overnight handover — 2026-09-17 → 2026-09-18

You said: *"go ahead and scope it out and build as much as you can as long as
this laptop is on you have full access am leaving for the day see you in the
morning."* Here's what got done, on branch `restore-admin-menu` (2 commits
ahead of `ambic/mdm-main`, clean fast-forward, nothing pushed/deployed —
see "What I deliberately did NOT do" below).

## 1. FCM wake channel — built, compiles clean, inert until you flip it on

Fixes "sync now doesn't work when the device is asleep." Full detail and
exact steps for you to do in the Firebase console: **[FCM-WAKE-SETUP.md](FCM-WAKE-SETUP.md)**.

Short version: it's a second, Doze-surviving push channel alongside the
existing WebSocket. Free, no re-enrollment, ships as a normal app update.
It does nothing today — `FcmSenderService.isConfigured()` is false until you
set `AMBIC_FCM_PROJECT_ID`, and the client has no Firebase config yet. Five
steps in that doc, ~15 minutes, all in the Firebase/Cloud console you already
used this morning for AMAPI.

## 2. Background app-inventory pre-scan — built, tested, committed

Fulfills: *"as soon as device is enrolled in the bg trigger auto scan of all
apps including system apps so they are ready when user wants to enter kiosk
mode."*

`DeviceOwnerInitializer.apply()` now warms an in-memory app list right after
Device Owner setup finishes; "Manage apps" in the kiosk admin menu reads from
that cache instead of scanning live. Verified: unit tests + full debug build
green, installed on an emulator, launched clean, no crash in logcat.

## What I deliberately did NOT do

Both of tonight's builds are **committed but not pushed to GitHub and not
released to the live 4-tablet fleet.** That's my own judgment call, not
something you asked for — you gave me full access, but with all 4 tablets
in production I didn't want to auto-promote new agent code to the fleet
overnight with nobody there to catch a problem. Worth a quick "yes keep doing
that" or "no, ship it yourself next time" from you so I calibrate correctly
going forward.

Server/console-only changes remained fair game under the same authorization
and there weren't any needed tonight — FCM and the app-inventory pre-scan are
both agent (client) code.

## Still open, not touched tonight (for you to prioritize)

- **`/design` MDM console redesign** — you asked for a modern/colorful
  redesign of the console (vs. the current black-and-white look), then
  immediately pivoted to the "2 devices we can't reset" request and it never
  got picked back up. Say the word and I'll pick it up fresh.
- **v0.2.23 fleet rollout status** — I don't have final confirmation whether
  the admin-menu-restoration rollout was ever promoted from canary to the
  full fleet, or is still sitting at canary. Worth checking the Rollouts
  screen first thing.
- **AMAPI integration plan** — a full second enrollment path via Google's
  Android Management API was scoped in an earlier plan file but not started;
  still just a plan, no code.

## Where things stand right now

- Working tree clean, `restore-admin-menu` branch, 2 new commits tonight
  (`bfe4d32` FCM, `6c8f35a` app-inventory cache), neither pushed.
- No changes touched the live server, database, or any deployed container —
  tonight was 100% local agent-code work.
