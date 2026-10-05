# Offline protection: Wi-Fi, full-screen warning, lockdown, unlock code

What a tablet does when it has no internet (agent v0.2.93 and later). The rules are numbers in
`core/.../net/ConnectivityPolicy.kt` and are unit-tested.

| Situation | What happens |
|---|---|
| Tablet boots | Wi-Fi is switched on at once, even if it was off. |
| Someone switches Wi-Fi off | After **3 minutes** it is switched back on and the tablet reconnects. |
| No working internet (validated connection) | The tablet retries Wi-Fi every 20 s (reconnect, then disconnect/reconnect every 5th try, then a radio power-cycle every 12th). Wi-Fi-off time counts as offline time. |
| **10 minutes** offline | Full-screen red message: "This device cannot be used without internet. Contact your administrator." with a live "trying to reconnect" line underneath. From now on it also hunts for open Wi-Fi networks once a minute and offers them to Android to join, and writes an **Offline report** (location fix, Wi-Fi state, open networks seen) to the event log every 2 minutes. Reports and logs reach the console on the first check-in that gets through; coming back online triggers one immediately. |
| **30 minutes** offline | **Complete lockdown**, saved across reboots. Nothing on the tablet can be used. |

## Unlocking a locked tablet
1. On the tablet tap **Administrator** and enter the **MDM exit password** (the one set with the kiosk, or the fleet admin passcode from the console's Settings).
2. If the tablet is offline, tap **Connect to Wi-Fi** and join a network (or a phone hotspot).
3. Tap **Trigger tablet unlock**. A 6-digit code is emailed to `MDM_CONSOLE_OTP_EMAIL` (default info@aradhanajewellers.com). It lasts 10 minutes, works once, allows 5 wrong tries; 3 codes per 10 minutes per tablet.
4. Type the code on the tablet. It returns to normal.

**Console alternative:** a tablet that is back online can be released with **Release lockdown** (Device > Control).

## Requirements and limits
* The server must be able to send email (`SMTP_HOST` etc. in `.env`). Without it "Trigger tablet unlock" says so; use **Release lockdown** from the console instead.
* A locked tablet needs *some* network to get the code: that is why the administrator panel can open Wi-Fi settings.
* Location reports need Location permission and location switched on (the agent switches it on as Device Owner). They are *logged*; the tablet cannot upload while it has no internet.
* Open-network hunting: Android only joins an open network that actually gives internet (captive-portal networks fail validation). Mobile data and SMS fallbacks are not built.
* Not yet tested on a real tablet.

## Shop closed hours (overnight Wi-Fi off)

The shop's router is switched off at night, so without an exception every tablet would show the full-screen "no internet" message
after 10 minutes and lock down after 30, and nobody could unlock them in the morning without the admin OTP.

**Console → Settings → Security → "Shop closed hours"** (default **22:00 to 08:00**, "Use shop hours" can be switched off).

- During those hours a tablet that is **sitting still** does not count time without internet: no full-screen message, no
  lockdown, no Wi-Fi hunting, no location reports. Nothing escalates.
- A tablet that is **carried away** (repeated motion from the motion sensor within 10 minutes) is guarded exactly as before, so
  a thief at night is not helped by the quiet window.
- When the shop opens, Wi-Fi is switched on immediately and the 10/30-minute clocks start from that moment, not from last night.
- A lockdown that has **already** happened is never released by this; it still needs the admin OTP.
- The server's "device stopped reporting" alert follows the same hours (and, in the morning, counts from opening time). The
  clock used is `MDM_SHOP_TZ` (default `Asia/Kolkata`); the devices use their own clock.
- Delivered to devices on their check-in (`guardQuietHours`), cached for offline use.

Code: `core/.../net/QuietHours.kt` and `ConnectivityPolicy` (agent), `common/.../util/QuietWindow.java` and `DeviceSilentTask`
(server), `GuardHoursPanel.tsx` (console). The timing rules are covered by `QuietHoursTest`.
