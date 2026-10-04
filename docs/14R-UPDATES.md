# Keeping the Redmi 14R up to date (wirelessly, automatically)

The Redmi 14R (model 2411DRN47C, China HyperOS, no Google services) is a Device Owner that was provisioned with this
laptop's **Android debug certificate**. Android refuses any update signed with a different key, so:

* the normal release APK (`mdmesh-agent.apk`) and the fleet's over-the-air rollout **cannot** update it;
* the only update that works is an APK built **here**, from the release's source, **signed with the same debug key**,
  installed in place with `adb install -r` (never uninstall, never clear data, never reset: that would drop Device Owner).

`tools/update-14r.py` does exactly that, automatically, every time a new GitHub release appears.

## What runs
Scheduled task **MDM 14R Updater** (this laptop, at logon and every 15 minutes) runs `tools/update-14r.py`:

1. finds the 14R in `adb devices` (by model); if it is not connected it just exits;
2. asks GitHub for the latest published release (for example `v0.2.96`) and works out its version code;
3. if the phone is already at that version or newer, exits;
4. checks the phone is still Device Owner of `com.mdmesh.agent`; if not, refuses and logs it;
5. builds `:app:assembleAospDebug -PchinaInPlaceReplacement=true` from **that release tag** in a throw-away git worktree
   (work in progress on this laptop never leaks in);
6. verifies the APK: package, version code, and that its signing certificate is the one on the phone;
7. installs with `adb install -r`, waits, and re-checks version and Device Owner. A failure is logged and not retried for 2 hours.

The finished APK is also kept in `C:\AradhanaSystems\handover\AmbicMDM-14R-<version>-cn-replace-debugsigned.apk`.
Log: `tools/logs/update-14r.log`. Run by hand any time: `python tools/update-14r.py` (`--dry-run`, `--build-only`, `--tag vX.Y.Z`).

## One-time setup (needs the phone in hand, once)
1. **Put the current build on it over USB** (USB cable, USB debugging on, File transfer mode, tap Allow):
   `adb install -r AmbicMDM-14R-0.2.95-cn-replace-debugsigned.apk` (or copy the file to the phone and open it).
   This build contains the agent's wireless-debugging keeper that older builds lack.
2. **Pair it for wireless adb**, the same way the tablets were: on the phone, Settings > Additional settings > Developer options >
   Wireless debugging > on > *Pair device with pairing code*; then on this laptop `adb pair <ip>:<pairing-port>` and enter the
   6-digit code. The existing task **MDM Wireless ADB Reconnect** then keeps it connected, reboot or not.
3. Wireless debugging only stays on while the phone is on a Wi-Fi network it has trusted; open that network once in the
   Wireless debugging screen and accept "Always allow on this network".

After that nothing is needed: a new release means the updater builds and installs it on the next 15-minute run, as long as
this laptop is on, on the same network, and the phone is awake and reachable.

## Limits you should know
* The laptop must be on and on the shop network. If it is off, the 14R simply stays on the old version until it is back.
* The 14R lags a release by up to 15 minutes plus the build time (about 4 to 8 minutes).
* It does **not** receive the fleet rollout, and the console's "update agent" on this device will fail; use this updater.
* The China build has no Google push wake-up (FCM); it relies on normal check-ins. All other features are identical.
* The debug key lives only on this laptop (`%USERPROFILE%\.android\debug.keystore`). **Back it up**: if it is lost, the 14R
  can no longer be updated in place and must be reset and re-provisioned with the release key.
* The clean long-term alternative is to factory-reset the 14R once and re-provision it with the **release-signed** China
  build, after which it follows the normal release rollout like the tablets. That needs your explicit approval (it wipes the phone).
