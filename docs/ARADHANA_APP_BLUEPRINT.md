# Aradhana Jewellers — App Layout Blueprint

Reference: Joyalukkas Android 7.8.7 (decompiled 2026-08-26).
**Rule: layout/UX patterns only. Zero Joyalukkas code, images, or assets reused.
All visuals come from `C:\Users\kaila\Desktop\Website Assets`.**

---

## 1. What the reference app actually is (decompile findings)

| Layer | Finding |
|---|---|
| Shell | React Native + Hermes bytecode (`index.android.bundle`, 6.9 MB) |
| Storefront UI | Magento PWA Studio web app loaded in `react-native-webview` |
| Trick used | Injected JS deletes the site's header/footer and hides its MUI bottom nav; the app renders **its own native bottom tabs** around the WebView |
| Backend | Magento GraphQL (`/graphql`), Apollo Client, CMS-driven home sections |
| Native modules | PayU + PhonePe payments, Zoho SalesIQ chat, Firebase (Crashlytics/Messaging), MoEngage push, cert pinning, root detection, ML Kit barcode |
| Home sections | `slider` → `banner` → `categoryList` → Shop By Gender / Occasion / Price / Style → `bestseller` |
| Screens | Splash/Launch, Maintenance, Offline, Product Listing, Product Detail, Search, Cart, Checkout, Orders, Wishlist, Account, OTP login, Gift Cards, Gold Scheme, Store Locator, PDF viewer, CMS pages |

### Takeaway for Aradhana
The "native app feel" = thin native shell (tabs, headers, payments, chat) + web/catalogue content inside. We can replicate this pattern with a much simpler stack — no Magento needed.

---

## 2. Recommended Aradhana architecture

- **React Native (bare or Expo)** with Hermes
- Content served from your existing JewelleryCatalogTool output (catalogue JSON/images) instead of Magento GraphQL
- Same shell pattern: native bottom tabs + native screens where it counts (enquiry/SIP/WhatsApp), catalogue browsing in-app

---

## 3. Screen map (Aradhana version)

### 3.1 Bottom Tabs (5)
1. **Home**
2. **Collections** (catalogue grid)
3. **Gold Rate** (daily rate board)
4. **SIP** (savings scheme)
5. **More** (About, Stores, Contact, WhatsApp, Instagram)

### 3.2 Home screen (top → bottom)
| Slot | Layout spec | Asset from Website Assets |
|---|---|---|
| Header | Logo + "Trusted Since 1995" strip; search icon; navy `#071B3A` bar | logo overlay (in assets) |
| Hero slider | Auto-scroll carousel, portrait-ish cards, dots indicator, silent video support | `01_Dashboard_Top_800x388` (3 banners) + `10_App_Video` |
| Quick categories | Horizontal scroll circles/tiles | derived from `07_Optional_450x450` |
| Middle banner strip | Single wide card per swipe | `02_Dashboard_Middle_800x272` (4 banners) |
| Shop By | Chip rows: Occasion / Price / Style (Aradhana equivalents) | text chips, no assets needed |
| Promo banners | Vertical stacked wide banners | `03_Web_Banners_1000x500` (6 banners) |
| New Arrivals / Bestseller | Horizontal product card rail → links to catalogue detail | product photos from Stock (NOT reference app's images) |
| Digital Catalogues | 2-col grid of covers → opens PDF/viewer | `06_Catalogue_Covers_1000x1000` (5 covers) |
| Footer CTA | Visit showroom / WhatsApp / Instagram buttons | `@Aradhanajewellers.boisar` link |

### 3.3 Collections screen
- Category chips (bangles, jhumka, rings, chains, …) sourced from Stock categories
- 2-col product grid, price-on-request toggle (gold rate × weight)
- Filters: category, weight band, purity (22K/18K)

### 3.4 Product Detail
- Swipeable image gallery, purity/weight/gross wt card
- Live estimate = weight × today's gold rate (your `stock_catalog.py` data)
- CTAs: **Enquire on WhatsApp**, **Visit Showroom**, Add to Wishlist
- No online checkout in v1 (matches single-store reality)

### 3.5 SIP screen
- Main creative hero + detailed terms section | `04_SIP` (800x650 main, 800x340 details)
- ⚠️ README note stands: scheme duration/amount/bonus fields stay placeholder until approved terms arrive
- CTA: register interest via WhatsApp/form

### 3.6 Gifting
- E-Gift Voucher creative | `05_E_Gift_Voucher` (600x350)

### 3.7 More tab
- About (Trusted Since 1995 story), Boisar showroom address + map link, phone/WhatsApp, Instagram deep link, FAQ

### 3.8 Utility screens
Splash (brand animation), Offline notice, Maintenance notice, Push-permission primer.

---

## 4. Brand tokens

| Token | Value |
|---|---|
| Primary | `#23519D` |
| Navy | `#071B3A` |
| Gold accent | `#E2B84C` |
| Font | Roboto (Regular / Medium / Mono available in assets pipeline) |
| Voice | Trusted Since 1995; Aradhya as campaign face alone — never together with Kishorji (permanent rule) |

## 5. Legal guardrails
- No Joyalukkas images, ornaments, icons, fonts, strings, or decompiled code in the shipped app
- Decomp output stays in `artifacts/joyalukkas_*` for reference only
- Product imagery must be Aradhana's own photography (Stock folder)

## 6. Decompile artifacts (for reference)
- Resources: `artifacts\joyalukkas_decoded`
- Java source: `artifacts\joyalukkas_src`
- Hermes string table: `artifacts\hermes_table.txt`
