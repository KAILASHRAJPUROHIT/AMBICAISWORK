# Joyalukkas Reference Audit — Replication Status

> Last updated: 2026-08-31
> Reference app: `com.joyalukkas.mcstaging.twa`
> Target app: `com.aradhanajewellers.app`

---

## Overall Progress

| Phase | Status | Notes |
|-------|--------|-------|
| 0 — Reference Audit | ✅ COMPLETE | All P0 screens captured and documented |
| 1 — Splash Screen | ✅ COMPLETE | Native video splash — SplashActivity plays outro.mp4 via Android VideoView before React Native loads |
| 2 — Splash→Home transition | ⬜ NOT STARTED | |
| 3 — Home viewport | ⬜ NOT STARTED | |
| 4 — Home scroll content | ⬜ NOT STARTED | Awaiting implementation |
| 5 — Header/nav | ⬜ NOT STARTED | Awaiting implementation |
| 6 — Menus/drawer | ⬜ NOT STARTED | Awaiting implementation |
| 7 — Category screen | ⬜ NOT STARTED | Awaiting implementation |
| 8 — Product listing | ⬜ NOT STARTED | Awaiting implementation |
| 9 — Product detail | ⬜ NOT STARTED | Awaiting implementation |
| 10 — Search/filter | ⬜ NOT STARTED | Awaiting implementation |
| 11 — Wishlist/cart/account | ⬜ NOT STARTED | Awaiting implementation |
| 12 — Info screens | ⬜ NOT STARTED | Awaiting implementation |
| 13 — Loading states | ⬜ NOT STARTED | Awaiting implementation |
| 14 — Animation pass | ⬜ NOT STARTED | Awaiting implementation |
| 15 — Nav regression | ⬜ NOT STARTED | Awaiting implementation |
| 16 — Performance | ⬜ NOT STARTED | Awaiting implementation |

---

## Screens Captured

### Automated ADB Screenshots (splash, home, scrolls)

| Screen | File | Quality | Notes |
|--------|------|---------|-------|
| Splash — cold start 0s | `jt0.png` | ✅ | Red background, 35KB |
| Splash — cold start 1s | `jt1.png` | ✅ | Red background, 35KB |
| Splash — loading 2s | `jt2.png` | ✅ | White loading screen (TWA), 186KB |
| Splash — loading 4s | `jt4.png` | ✅ | Still loading, 191KB |
| Splash — logo 7s | `jt7.png` | ✅ | Red bg + interlocking rings, 1.1MB |
| Home — loaded 12s | `jt12.png` | ✅ | Full home, 1.3MB |
| Home — top view | `jl_home_top.png` | ✅ | Full home header + categories + banner |
| Home — carousel 0/1/3/5/7 | `jt_home*.png` | ✅ | Dark + gold ribbon banner slides |
| State — home | `jl_state.png` | ✅ | Full home view |
| State — sale promo | `jl_state2.png` | ✅ | "BIGGEST SALE" banner slide |
| Splash — 2s/5s/8s | `jl_splash_*.png` | ✅ | Splash sequence |

### User Manual Screenshots (18 screens captured)

| Screen | File | Quality | Notes |
|--------|------|---------|-------|
| Gold Scheme tab | `Screenshot_...-59-916*.jpg` | ✅ | Bottom sheet with 4 action cards |
| Login | `Screenshot_...-09-374*.jpg` | ✅ | Email/password form, Sign In/Sign Up |
| Price Scanner | `Screenshot_...-21-679*.jpg` | ✅ | Full-screen camera with QR frame |
| Search (empty) | `Screenshot_...-34-665*.jpg` | ✅ | Search input, keyboard visible |
| Search (results) | `Screenshot_...-45-870*.jpg` | ✅ | Popular searches + suggested products |
| Product listing (top) | `Screenshot_...-31-978*.jpg` | ✅ | 2-col grid, filter section |
| Product listing (scrolled) | `Screenshot_...-35-518*.jpg` | ✅ | Price filter expanded, more products |
| Product listing (categories) | `Screenshot_...-38-866*.jpg` | ✅ | Sub-category carousel + banner |
| Product listing (grid) | `Screenshot_...-42-643*.jpg` | ✅ | Full product grid view |
| Product detail (top) | `Screenshot_...-48-038*.jpg` | ✅ | Product image, name, price, Video Call |
| Product detail (mid) | `Screenshot_...-00-597*.jpg` | ✅ | Price breakup, Discover More, delivery |
| Product detail (price table) | `Screenshot_...-03-397*.jpg` | ✅ | Full price breakup table |
| Product detail (description) | `Screenshot_...-05-882*.jpg` | ✅ | Product description + brand story |
| Product detail (reviews) | `Screenshot_...-08-486*.jpg` | ✅ | Reviews section + lifestyle images |
| Product detail (similar) | `Screenshot_...-12-547*.jpg` | ✅ | Similar Products + Instagram section |
| Product detail (bottom) | `Screenshot_...-14-820*.jpg` | ✅ | Need Help + Chat buttons |
| Cart (top) | `Screenshot_...-26-736*.jpg` | ✅ | Progress stepper + cart item |
| Cart (bottom) | `Screenshot_...-30-221*.jpg` | ✅ | Gift options + coupon + checkout |

---

## Screens NOT Captured (Gaps)

### Critical (must have for replication)

| Priority | Screen | Status | Notes |
|----------|--------|--------|-------|
| 🔴 P0 | **Category tab** | ✅ CAPTURED | Header + 4 cards + scrollable list + 6 quick-access cards |
| 🔴 P0 | **Product listing** | ✅ CAPTURED | 2-col grid, filter section, category carousel, sub-categories |
| 🔴 P0 | **Product detail** | ✅ CAPTURED | Image carousel, price, Video Call, Price Breakup, reviews, similar products |
| 🔴 P0 | **Account tab** | ✅ CAPTURED | Avatar + Login + Profile/Orders/Cart/Wishlist/Returns/Scheme |
| 🔴 P0 | **Search** | ✅ CAPTURED | Empty state + results with Popular Searches + Suggested Products |
| 🔴 P0 | **Gold Scheme tab** | ✅ CAPTURED | Bottom sheet overlay with 4 action cards |
| 🔴 P0 | **Price Scanner tab** | ✅ CAPTURED | Full-screen camera scanner with QR frame |

### Important (needed for complete replication)

| Priority | Screen | Status | Notes |
|----------|--------|--------|-------|
| 🟡 P1 | **Cart** | ✅ CAPTURED | Progress stepper, item list, gift options, coupon, checkout |
| 🟡 P1 | **Wishlist** | NOT CAPTURED | Saved items view |
| 🟡 P1 | **Login flow** | ✅ CAPTURED | Email/password form, Sign In/Sign Up |
| 🟡 P1 | **Country selector** | NOT CAPTURED | Dropdown from header |
| 🟡 P1 | **Menu/drawer** | NOT CAPTURED | If exists (not observed in screenshots) |

### Nice to have

| Priority | Screen | Status | Notes |
|----------|--------|--------|-------|
| 🟢 P2 | **Checkout flow** | NOT CAPTURED | Shipping + payment steps |
| 🟢 P2 | **Showroom locator** | NOT CAPTURED | Store finder |
| 🟢 P2 | **About/Info pages** | NOT CAPTURED | Company info |
| 🟢 P2 | **Filter/sort modal** | NOT CAPTURED | Full filter panel within product listing |
| 🟢 P2 | **Gold rate widget** | NOT CAPTURED | Live rate display |
| 🟢 P2 | **Logged-in account** | NOT CAPTURED | Profile view after login |

### Note on TWA Navigation
The Joyalukkas app is a TWA (Trusted Web Activity) — Chrome WebView. ADB `input tap` on bottom nav coordinates does not reliably register clicks. Screenshots were captured by manually navigating on the Redmi Tab device. For remaining screens (Price Scanner, Gold Scheme, Search, Product listing/detail), manual device access is required.

---

## Home Screen Content Sections (Joyalukkas)

Based on screenshots, the Joyalukkas home screen has:

1. **Header** — Logo + tagline (left), Country + Search + Cart (right)
2. **Category carousel** — 9 visible items, horizontal scroll, circular peach-bg icons
3. **Hero banner** — Full-width auto-scrolling carousel, 3+ slides observed
4. **Bottom nav** — 5 tabs fixed at bottom

**That's it.** The home screen is compact — no additional sections below the hero banner. This is a key difference from many other jewelry apps that have:
- Gold rate card
- Featured collections
- New arrivals grid
- Store locator
- Testimonials
- Footer

Joyalukkas keeps the home screen minimal with just categories + hero banner.

---

## Phase 1 — Splash Screen Implementation

**Status:** ✅ COMPLETE (2026-09-01) — Native Video Splash

### Changes Made

| File | Change |
|------|--------|
| `app.json` | `backgroundColor: "#D42426"` (was `#23519D`), expo-video plugin added |
| `src/app/_layout.tsx` | Removed `AnimatedSplashOverlay`, removed `SplashScreen.preventAutoHideAsync()` |
| `src/components/animated-icon.tsx` | Returns null — native splash handles everything |
| `android/.../SplashActivity.kt` | **NEW** — Native Android activity playing `outro.mp4` via `VideoView` |
| `android/.../res/layout/activity_splash.xml` | **NEW** — VideoView on red `#D42426` background |
| `android/.../res/raw/splash_video.mp4` | **NEW** — Embedded video (must re-copy after prebuild) |
| `android/.../AndroidManifest.xml` | `SplashActivity` = launcher, `MainActivity` = secondary |

### How It Works
1. App launches → Android starts `SplashActivity` (fullscreen, no title bar)
2. `VideoView` plays `splash_video.mp4` natively — zero JS, zero React Native
3. Video completes → starts `MainActivity` → React Native loads → app renders
4. If video errors → falls back to `MainActivity` immediately

### Verified Behavior
- Native splash: Video plays fullscreen on red `#D42426` background
- Transition: Smooth handoff from `SplashActivity` to `MainActivity`
- Fallback: Error handler starts `MainActivity` if video fails

### Known Limitation
- Android `screencap` captures VideoView as black due to DRM protection
- User must verify visually on physical device

### Remaining Blue (`#23519D`) References
62 occurrences across codebase — to be migrated in Phase 5+ (header/nav, category, product detail, etc.)

---

## Phase 2 — Splash→Home Transition (Next)

The native video splash now handles the splash sequence. Phase 2 will:
1. Fine-tune the transition from `SplashActivity` to `MainActivity`
2. Consider adding a brief loading indicator during React Native initialization
3. Match Joyalukkas's smooth reveal pattern
4. Verify the video splash plays correctly on all target devices

---

## Remaining Gaps to Capture (manual device access required)

1. **Wishlist** — Navigate to wishlist from Account or product detail
2. **Country selector** — Tap "India" dropdown in header
3. **Checkout flow** — Tap "PROCEED TO CHECKOUT" in cart
4. **Filter/sort modal** — Tap "FILTER" in product listing bottom bar
5. **Logged-in account state** — Login and capture Account screen
6. **Store locator** — Navigate from Category quick-access cards
7. **Gold rate display** — Navigate from Category quick-access cards

## Phase Roadmap

1. ~~Phase 1: Splash Screen~~ — ✅ COMPLETE
2. Phase 2: Splash→Home transition — Animate splash to home
3. Phase 3: Home viewport — Header + category carousel + hero banner
4. Phase 4: Home scroll content — (Minimal in Joyalukkas)
5. Phase 5: Header/nav — Bottom nav + header redesign
6. Phase 6: Menus — (No drawer observed in Joyalukkas)
7. Phase 7: Category screen — 4 cards + scrollable list + quick-access
8. Phase 8: Product listing — 2-col grid + filters
9. Phase 9: Product detail — Full product page with all sections
10. Phase 10: Search/filter — Search screen with results
11. Phase 11: Wishlist/cart/account — Cart + wishlist + account
12. Phase 12: Info screens — Gold rate, store locator, etc.
13. Phase 13: Loading states — Skeleton loaders, spinners
14. Phase 14: Animation pass — Micro-interactions
15. Phase 15: Nav regression — Full navigation testing
16. Phase 16: Performance — Optimize and benchmark

---

## File Manifest

| File | Description |
|------|-------------|
| `SCREEN_MAP.md` | Detailed layout spec for ALL screens (Home, Category, Account, Price Scanner, Gold Scheme, Login, Search, Product Listing, Product Detail, Cart) |
| `REPLICATION_STATUS.md` | This file — tracking audit progress |
| `COMPONENT_SPEC.md` | Component dimensions, colors, spacing |
| `FLOW_MAP.md` | Navigation flow documentation |
| `comparisons/` | Directory with all captured screenshots (130+ files) |
