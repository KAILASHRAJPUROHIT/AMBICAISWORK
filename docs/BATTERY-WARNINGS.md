# Low-battery warnings

| Battery | Stage | Colour |
|---|---|---|
| 31% and above, or charging | normal | none |
| 21 to 30% | yellow | `#F2C230` |
| 11 to 20% | orange | `#F28C28` |
| 10% and below | red | `#E5484D` |

**On the tablet / phone**
- A coloured frame is drawn round the whole screen of every MDM screen (`BatteryBorder`, a foreground drawable on the window), so the
  edge of the kiosk, the agent screens, the guard screens and the update popup all show it.
- The kiosk header's battery pill and ring take the colour, and a bilingual banner (English over Hindi) appears under the clock card.
- Each time the stage gets worse (at 30, 20 and 10%) the tablet plays an error tone and then the voice note "Battery low, charge now"
  in English and Hindi. At 10% and below it repeats every 2 minutes until the tablet is charging. Plugging in clears everything.
- Volume is always 50% of the alarm volume, whether the tablet is muted or not (the earlier volume is restored afterwards).
- Nothing plays while the screen is off. A tablet that restarts already low does not play on its first reading.
- The first drop is announced at 30% (the yellow stage starts at 30), not at 29%.

**Voice note.** Put the recording at `agent-android/app/src/main/res/raw/battery_low_voice.mp3` (or `.ogg` / `.wav`; the file name
without extension must be `battery_low_voice`) and release. Until then the tablet reads the sentence with its own text-to-speech
voices (English, and Hindi only if a Hindi voice is installed).

**Console.** The battery bar and ring on the device list, the overview and the device page use the same colours.

Code: `core/.../battery/BatteryStage.kt` (rules, unit tested), `app/.../battery/` (`BatteryAlertController`, `BatteryAlertPlayer`,
`BatteryBorder`), `KioskLauncherActivity` (pill and banner), `web/src/ui/battery.ts`.
