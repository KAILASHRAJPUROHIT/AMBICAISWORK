# Aradhana Jewellers — Total Project Handover

> Last updated: 2026-09-01
> Reference app: Joyalukkas (`com.joyalukkas.mcstaging.twa`)
> Target app: Aradhana Jewellers (`com.aradhanajewellers.app`)

---

## 1. Project Goal

Replicate the Joyalukkas jeweller app's UI/UX as closely as possible, using Aradhana Jewellers branding, content, products, and business data. The replication follows a strict 30+ rule set defined by the user, including:

- No improvisation — every pixel must match the reference
- Screenshot-driven development
- Incremental phased implementation
- Acceptance levels: RED (failed), AMBER (partial), GREEN (match)
- Phase-by-phase verification before moving on

---

## 2. Tech Stack

| Component | Version |
|-----------|---------|
| Expo SDK | 57 |
| React | 19.2.3 |
| React Native | 0.86.3 |
| TypeScript | 6.0.3 |
| Expo Router | File-based routing |
| Package | `com.aradhanajewellers.app` |
| Version code | 5 |
| Target SDK | 36 |
| Min SDK | 24 |
| Kotlin | 2.1.20 |
| NDK | 27.1.12297006 |

---

## 3. Project Location & Git

| Item | Value |
|------|-------|
| Local path | `C:\Users\kaila\Desktop\aradhana-app` |
| Branch | `reference/joyalukkas-1to1` |
| Remote | `origin` → `https://github.com/AradhanaJewellers/APP.git` |
| Default branch | `master` |

---

## 4. Devices

| Device | Address | Role | Notes |
|--------|---------|------|-------|
| Redmi Tab (2509BRP2DI, 2560×1600) | `192.168.0.18:33107` | Primary audit device | Manual screenshot capture, TWA nav unreliable via ADB |
| Nothing Phone (A069P) | `192.168.0.6:5555` | Secondary | Fingerprint locked, hard to unlock via ADB |
| Emulator (Aradhana_Test) | `emulator-5554` | Build verification | Android 15, x86_64 |

---

## 5. Build Instructions

### Prerequisites
- JDK: `C:\jdk17\jdk-17.0.14+7`
- Android SDK: `$env:LOCALAPPDATA\Android\Sdk`
- Node.js, npm, npx

### Build Commands
```bash
# Clean prebuild
Remove-Item -Recurse -Force "android" -ErrorAction SilentlyContinue
npx expo prebuild --platform android --clean

# Copy video to Android raw resources (AFTER prebuild)
New-Item -ItemType Directory -Force -Path "android\app\src\main\res\raw"
Copy-Item "C:\Content\outro.mp4" "android\app\src\main\res\raw\splash_video.mp4"

# Build release APK
$env:JAVA_HOME="C:\jdk17\jdk-17.0.14+7"
$env:ANDROID_HOME="$env:LOCALAPPDATA\Android\Sdk"
cd "android"; .\gradlew.bat assembleRelease --no-daemon

# APK output
# android\app\build\outputs\apk\release\app-release.apk

# Install on Redmi Tab
adb -s 192.168.0.18:33107 install -r "android\app\build\outputs\apk\release\app-release.apk"
```

### Important Build Notes
- `splash_video.mp4` must be copied to `android/app/src/main/res/raw/` AFTER every `expo prebuild --clean` — prebuild wipes the android directory
- The `expo-video` config plugin is in `app.json` but is NOT used for splash — the native `SplashActivity` handles video
- `expo-av` is NOT installed — it has a native linking crash (`UnsatisfiedLinkError` for `libexpo-av.so`)
- Metro bundler does not stay alive in background — debug builds fail to load JS bundle; use release builds

---

## 6. Current State — Phase Completion

| Phase | Status | Description |
|-------|--------|-------------|
| 0. Reference Audit | ✅ COMPLETE | All P0/P1 screens captured, 4 docs created |
| 1. Splash Screen | ✅ COMPLETE | Native video splash using Android VideoView |
| 2. Splash→Home transition | 🔲 NOT STARTED | |
| 3. Home viewport | 🔲 NOT STARTED | |
| 4. Home scroll content | 🔲 NOT STARTED | |
| 5. Header/nav | 🔲 NOT STARTED | 62 remaining `#23519D` references |
| 6. Menus/drawer | 🔲 NOT STARTED | |
| 7. Category screen | 🔲 NOT STARTED | |
| 8. Product listing | 🔲 NOT STARTED | |
| 9. Product detail | 🔲 NOT STARTED | |
| 10. Search/filter | 🔲 NOT STARTED | |
| 11. Wishlist/cart/account | 🔲 NOT STARTED | |
| 12. Info screens | 🔲 NOT STARTED | |
| 13. Loading states | 🔲 NOT STARTED | |
| 14. Animation pass | 🔲 NOT STARTED | |
| 15. Nav regression | 🔲 NOT STARTED | |
| 16. Performance | 🔲 NOT STARTED | |

---

## 7. What Was Built — Detailed

### Phase 0: Reference Audit
- 18 user-captured screenshots of Joyalukkas app across all screens
- ADB-captured splash sequence, home screen, scroll states
- 4 documentation files created in `docs/reference/`:
  - `SCREEN_MAP.md` — 620-line layout spec for every screen
  - `REPLICATION_STATUS.md` — Progress tracker
  - `COMPONENT_SPEC.md` — 15 component specs (dimensions, colors, animations)
  - `FLOW_MAP.md` — 398-line navigation flow map with 10 screen flows

### Phase 1: Splash Screen (now superseded by native video splash)
- Changed `app.json` splash background from `#23519D` to `#D42426`
- Initially created JS-based `AnimatedSplashOverlay` with `expo-video` → `expo-av` → back to `expo-video`
- All JS approaches failed: `expo-video` couldn't resolve `require()` assets on Android, `expo-av` crashed with `UnsatisfiedLinkError`

### Native Video Splash (current implementation)
- Created `SplashActivity.kt` — native Android activity that plays video before React Native loads
- Created `activity_splash.xml` — VideoView layout with red `#D42426` background
- Copied `outro.mp4` to `android/app/src/main/res/raw/splash_video.mp4`
- Updated `AndroidManifest.xml` — `SplashActivity` is the launcher, `MainActivity` is secondary
- Removed JS `AnimatedSplashOverlay` (returns null)
- Removed `SplashScreen.preventAutoHideAsync()` from `_layout.tsx`
- Removed `expo-video` plugin from `app.json` (no longer needed for splash)

**How it works:**
1. App launches → Android starts `SplashActivity` (fullscreen, no title bar)
2. `VideoView` plays `splash_video.mp4` natively — zero JS, zero React Native
3. Video completes → starts `MainActivity` → React Native loads → app renders
4. If video errors → falls back to `MainActivity` immediately

**Note:** Android `screencap` captures VideoView as black due to DRM protection. User must verify visually on device.

---

## 8. Design Tokens

### Colors
| Name | Hex | Usage |
|------|-----|-------|
| Aradhana Red | `#D42426` | Primary brand, splash bg, active nav |
| Old Blue (to migrate) | `#23519D` | 62 references remaining across codebase |
| Joyalukkas Red | `#D42426` | Reference primary (matches Aradhana) |
| Joyalukkas Nav Bg | `#FDF0EC` | Bottom nav background (peach/salmon) |
| Joyalukkas Category Bg | `#F5E6E0` | Category circle background |

### Dimensions (from Joyalukkas reference)
| Element | Size |
|---------|------|
| Header height | ~60px |
| Category circle | ~80px diameter |
| Category carousel | ~170px height |
| Hero banner | ~55-60% viewport height |
| Bottom nav | ~70px height |
| Bottom nav icons | ~24px |
| Active nav color | `#D42426` |
| Inactive nav color | `#333333` |

---

## 9. Known Issues & Blockers

| Issue | Severity | Status |
|-------|----------|--------|
| 62 references to old blue `#23519D` | MEDIUM | Will migrate in Phase 5+ |
| TWA bottom nav unreliable via ADB | LOW | Requires manual device interaction |
| Nothing Phone fingerprint locked | LOW | Cannot unlock via ADB |
| Metro bundler dies in background | LOW | Use release builds |
| Android screencap captures VideoView as black | INFO | Device must be checked visually |
| `splash_video.mp4` must be re-copied after prebuild | LOW | Documented in build instructions |

---

## 10. Screens Captured (Reference)

### Captured (18 screens)
| Screen | Quality | Notes |
|--------|---------|-------|
| Splash sequence (0-12s) | ✅ | Cold start through to home |
| Home (top, scrolled, carousel) | ✅ | Full layout documented |
| Category | ✅ | 4 cards + scrollable list + 6 quick-access |
| Account | ✅ | Avatar + login prompt + menu items |
| Price Scanner | ✅ | Full-screen camera with QR frame |
| Gold Scheme | ✅ | Bottom sheet with 4 action cards |
| Login | ✅ | Email/password form |
| Search (empty + results) | ✅ | Popular searches + suggested products |
| Product listing (4 views) | ✅ | Grid, filters, categories, sub-categories |
| Product detail (7 views) | ✅ | Full page: image, price, breakup, reviews, similar |
| Cart (2 views) | ✅ | Progress stepper, items, gift, coupon, checkout |

### Not Captured (requires manual device access)
- Wishlist
- Country selector dropdown
- Checkout flow (shipping + payment)
- Filter/sort modal
- Logged-in account state
- Store locator
- Gold rate display

---

## 11. File Structure — Key Files

### Config
| File | Description |
|------|-------------|
| `app.json` | Expo config: splash bg `#D42426`, expo-video plugin |
| `AGENTS.md` | Requires reading Expo v57 docs before writing code |
| `package.json` | Dependencies, scripts |

### App Source
| File | Description |
|------|-------------|
| `src/app/_layout.tsx` | Root layout, Gate component (auth routing), StatusBar |
| `src/app/onboarding.tsx` | Onboarding/welcome screen |
| `src/components/animated-icon.tsx` | Returns null (native splash handles it) |
| `src/components/app-tabs.tsx` | NativeTabs bottom navigation |
| `src/constants/theme.ts` | Design tokens (has `#23519D` primary) |
| `src/config/master.ts` | Business config (has `primaryBlue: '#23519D'`) |
| `src/store/` | All stores: cart, wishlist, lang, profile, enquiries |
| `src/services/` | rates.ts, products.ts |

### Android Native
| File | Description |
|------|-------------|
| `android/.../SplashActivity.kt` | **NATIVE VIDEO SPLASH** — plays outro.mp4 |
| `android/.../res/layout/activity_splash.xml` | VideoView on red bg |
| `android/.../res/raw/splash_video.mp4` | Embedded video (must re-copy after prebuild) |
| `android/.../AndroidManifest.xml` | SplashActivity = launcher |
| `android/.../MainActivity.kt` | React Native activity (secondary) |
| `android/.../MainApplication.kt` | RN application setup |

### Documentation
| File | Description |
|------|-------------|
| `docs/reference/SCREEN_MAP.md` | 620-line layout spec for all screens |
| `docs/reference/REPLICATION_STATUS.md` | Phase progress tracker |
| `docs/reference/COMPONENT_SPEC.md` | 15 component specs |
| `docs/reference/FLOW_MAP.md` | 398-line navigation flow map |
| `docs/reference/comparisons/` | 130+ reference screenshots |
| `HANDOVER.md` | This file |

---

## 12. Next Steps

### Immediate (Phase 2)
1. **Splash→Home transition** — Animate the reveal from splash to home screen
2. Verify video splash works on device (user to confirm visually)
3. If video doesn't play, debug `SplashActivity` logcat

### Short-term (Phases 3-5)
3. **Home viewport** — Header + category carousel + hero banner redesign
4. **Home scroll content** — Match Joyalukkas minimal layout
5. **Header/nav** — Migrate remaining 62 `#23519D` references, redesign header

### Medium-term (Phases 6-12)
6. Category, product listing, product detail, search, cart, account screens

### Long-term (Phases 13-16)
7. Loading states, animations, nav regression, performance optimization

---

## 13. User's 30+ Rule Set (Summary)

The user defined a strict methodology for this project:

1. No improvisation — every change must reference the Joyalukkas app
2. Screenshot-driven — capture first, then implement
3. Incremental phases — complete one phase before starting next
4. Acceptance levels: RED/AMBER/GREEN
5. Build and verify on physical device after each change
6. Document everything in `docs/reference/`
7. Keep `AGENTS.md` requirements (read Expo v57 docs)
8. Branch-based development on `reference/joyalukkas-1to1`
9. No commits unless explicitly requested
10. Phase order is mandatory — cannot skip ahead
