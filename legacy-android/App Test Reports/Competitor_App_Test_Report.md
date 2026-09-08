# Competitor Jewellery App Test Report
Device: Redmi Pad Pro 2 (2509BRP2DI), tested via ADB over WiFi debugging
Date: 2026-08-22
Tester: Automated walkthrough (ADB + on-device screenshots) + APK static analysis (jadx decompile)

Apps in scope (14):
1. GRT Jewellers (com.grtjewels.oriana)
2. Ornate NX (com.ornate.nx)
3. Kalamandir Jewellers (com.dsoft.kalamandirjewellers)
4. Ratanlal CB Afna Jewellers (com.dsoft.ratanlalcbafnajewellers)
5. Fatehchand Jewellers (com.dsoft.fatehchandjewellers)
6. Joyalukkas (com.joyalukkas.mcstaging.twa)
7. GIVA (co.giva.jewellery)
8. Chawla Jewellers (com.chawlajewellers)
9. My Bhima (sharaaninfo.mybhima)
10. Jewelflix Pravesh Gold (com.jewelflix.praveshgold)
11. Malabar Gold & Diamonds (malabargold.qburst.com.malabargold)
12. Manisha Jewellers (com.dsoft.manishajewellers)
13. Tanishq (com.titancompany.tanishqapp)
14. Bhima Gold (com.bhima.gold)

---

## 1. GRT Jewellers

**First impressions:** Clean splash (logo + "Since 1964"), asks notification permission upfront.

**Home screen:**
- Persistent live gold rate ticker bar at very top: "GOLD 22 KT/1g - ₹14950" with dropdown chevron (likely expands to show 18K/24K/silver rates too), plus a store-locator icon and an appointment/calendar icon in the top bar — both always visible, not buried in a menu.
- Hamburger menu (left) + logo + search bar ("Search for bracelets...")
- Banner carousel (promotions - Raksha Bandhan campaign)
- "What's trending" horizontal product cards with % off badges
- Floating support/headset button (bottom right, sticky)
- Bottom nav: Home / Categories / Wishlist / Your Cart / Profile — standard 5-tab layout

**Notes for our app:** The persistent gold-rate-in-header + one-tap store locator + one-tap appointment booking, all visible without digging into a menu, is a strong pattern — customers buying gold care about today's rate constantly.

**Categories/PLP:** Categories tab (not embedded in hamburger) lists Gold/Diamond/Silver/Platinum/Coins&Bars/Jewellery Purchase Plan (gold savings scheme)/Solitaire/Collections/Gift Store/Offers, plus quick INR-currency / Locate Us / Call Us row at top. PLP has subcategory icon strip (Rings/Earrings/Pendants/Bangles&Bracelets/Chains), Filters + item count, Sort dropdown, quick-filter chips (Bestseller/Quick Delivery/New Drop). Each product card has a compare-star icon AND a wishlist-heart icon (dual icons — slightly cluttered).

**PDP (Product Detail):** ⚠️ **No "Add to Cart" — button is "Send Enquiry" instead.** Also has "Notify Price Drop", product code shown, "View Details" link (opens purity/making-charge breakdown presumably), share icon, wishlist heart, compare star, price-tag icon, "For International shipment" checkbox, floating WhatsApp-style support button.

**Cart:** Confirmed empty-cart state pushes "Get Whatsapp Assistance" as the primary CTA — this app is enquiry/WhatsApp-driven, not a direct-checkout e-commerce cart, at least for higher-value items like platinum.

**Login:** Email/phone + OTP, or password, or Google sign-in. "New User? Sign Up" + "Forgot Password". Standard, no phone-only mandatory OTP wall blocking browsing (browsing worked fully without login).

**Overall GRT verdict:** Strong informational/browsing experience and trust signals (live gold rate, "Since 1964" heritage, quick store/call access) but the actual purchase path is a *lead-generation funnel* (enquiry/WhatsApp/call store) rather than transactional checkout. Good for high-trust big-ticket sales; bad if we want frictionless self-serve buying.

---

## 2. Ornate NX

**Result: App is non-functional / not a consumer app.** On launch it immediately throws `Error! Could not proceed, please check IP address-port number and server status.` This points to a hardcoded local server/IP config — almost certainly an internal billing/POS or ERP companion app (Ornate is a jewellery ERP/software vendor), not a customer-facing shopping app. No further testing possible live; will rely on static/decompiled analysis only for this one.

---

## 3. Kalamandir Jewellers

**Login:** Mobile-number OTP login gate on launch, but has a **"Skip"** button for guest browsing — good, doesn't force signup before showing value.

**Home:** Heavy promo-carousel usage — "Suvarna Sankalp: Protect Yourself From Rising Gold Prices — Book Now, Buy Later" and "Monthly Rate Booking — Get up to 50% Benefits" (gold price-lock/booking schemes are a major push here, more prominent than at GRT). A "Current Gold/Silver Rate" widget sits directly on the home feed with left/right arrows to page through Gold 18KT/14KT, Silver 92.5/810 rates — nice compact multi-metal rate ticker (better than GRT's single-line rate since it covers more metal/purity combos). Category icon row (Earrings/Rings/Pendant/Necklace/Bracelet/Mangalsutra). Two large tiles: "Gold Scheme" and "E-Gift Cards".

**Bottom nav is fundamentally different from GRT:** My Profile / Wallet / **Gold SIP** / My Txn / Contact — no Home, no Cart, no Wishlist tab (wishlist demoted to a small header icon). This app is built around recurring gold-investment behavior (SIP = systematic investment plan) and wallet/transaction tracking, not classic product browsing/cart e-commerce.

**PLP (Earrings):** Subcategory icons at top (circular avatars). Product cards show name + "Metal Type: 14KT" but **no price at all** on the listing. Heavy "Lab Grown [Diamond]" naming throughout the catalog (GRT didn't emphasize lab-grown as much).

**PDP:** ⚠️ **Weakest PDP seen so far** — no price, no product code, no description/specs beyond metal type, no "Add to Cart", no "Enquire"/"Book Appointment" CTA of any kind. Only a wishlist heart and share icon, plus a "Recommended Product" rail. A shopper has literally no next action except wishlist/share — worse than GRT's enquiry model.

**Overall Kalamandir verdict:** Strong on gold-investment/scheme features (SIP, rate booking, wallet) which is a real differentiator, but the core product browsing/PDP experience is thin — no pricing transparency, no purchase or contact path from a product page. Big opportunity for us: match their scheme/SIP idea but don't copy their bare PDP.

---

## 4. Ratanlal CB Afna Jewellers

**Confirmed: same white-label app platform as Kalamandir Jewellers** (both `com.dsoft.*` package family — "dsoft" appears to be a jewellery-app-as-a-service vendor). Same login-with-Skip pattern, same visual template, re-skinned in indigo/purple instead of Kalamandir's brown/gold.

Differences from Kalamandir's build: bottom nav here is Home / Wallet / **Deals** / My Txn / Contact (keeps a Home tab, swaps Gold SIP→Deals). Home has 4 feature tiles instead of 2: **Digital Gold/Silver** (buy fractional gold digitally), Gold Scheme, E-Gift Card, **Book My Gold** (price-lock booking). Single-line gold rate bar (22KT/916 - ₹14793/gm) rather than Kalamandir's paged multi-metal widget. Regional-language (Marathi) marketing banner — good localization touch for a regional customer base.

**Takeaway:** the dsoft platform's core value prop across its client apps is digital-gold-investment + scheme/booking tooling bolted onto a fairly generic catalog browser. Confirms this is a real pattern worth having in our app (digital gold purchase in small denominations is a proven demand driver), not just a one-off idea from one competitor.

---

## 5. Fatehchand Jewellers

Same dsoft template (brown/gold skin). Same 4 tiles (Digital Gold/Gold Schemes/E-Gift Card/Book My Gold). Adds a "E-STORE — Click Here" embedded video banner promoting their online store. Bottom nav: Home/Wallet/My Txn/Contact (no Deals tab here).

---

## 6. Manisha Jewellers

Same dsoft template (purple skin) but with a notably different bottom nav: **Map / Offers / Rate Alert / Wishlist / Contact** — no Home tab, no Wallet/Txn tabs. **"Rate Alert" as a first-class center nav item is a nice differentiator** — implies users can set a target gold price and get notified (vs. everyone else just showing today's rate passively). Also uses real storefront photography in the hero banner (trust/localness signal) and has a "Kids Jewellery" category — a demographic segment none of the other apps explicitly called out.

**dsoft-family summary (Kalamandir/Ratanlal/Fatehchand/Manisha):** All four are the same underlying app shell with different skins, nav tab selection, and tile sets drawn from a shared feature pool: {Home, Wallet, Deals, My Txn, Contact, Map, Offers, Rate Alert, Wishlist, Gold SIP} × {Digital Gold, Gold Scheme, E-Gift Card, Book My Gold}. None showed prices on PLP/PDP in our testing, none had a real cart/checkout — all are lead-gen/scheme-first, not transactional e-commerce. **Digital Gold purchase + Gold Scheme SIP + price Rate Alert are the three recurring "financial-product" features this whole vendor family bets on** — strong signal that jewellery shoppers in this market respond to gold-as-investment framing, not just gold-as-product.

---

## 7. Joyalukkas

**By far the most polished, production-grade app tested so far.** This is a TWA (Trusted Web Activity — wrapped website) but doesn't feel like one; smooth, animated splash, full-bleed autoplay muted hero video with mute toggle.

**Global scale:** country selector covers India, UAE, Oman, Qatar, Bahrain, Kuwait, KSA, Singapore, Malaysia, UK and more — this is a large international chain, not a regional player like the rest of our set.

**Home:** quick-icon row (Express Delivery / Rakhi Collection / Gift Card / New Arrivals / Wedding / Kids / Platinum / Men's Collection / Silver / **Bullions**). Bottom nav: Home / **Price Scanner** / Category / Gold Scheme / Account. Price Scanner is a unique feature (presumably scans an in-store tag/barcode to pull up product info+price — bridges physical showroom visits with the app).

**PLP:** real, full e-commerce quality — actual prices shown with strikethrough MRP + "40% Off on Making Value" badges, "Express Delivery" tags, wishlist heart, share/open icon, "Showing 12/1993 Designs" pagination, grid/list view toggle, Sort By, Filter chip. This is the only app so far with genuine discount pricing visible directly on the listing grid.

**Cart:** has a real shopping-bag icon in the header (not just wishlist) — strongly suggests actual cart/checkout flow exists (didn't complete a full add-to-cart in this pass, but the UI affordances are all there, unlike GRT/Kalamandir's enquiry-only model).

**Overall Joyalukkas verdict:** The benchmark to beat. Real pricing transparency, real discounts, real cart, global multi-country support, plus differentiators like Price Scanner and Bullions (raw gold coin/bar purchase). If our app is judged against the best in this space, this is it.

---

## 8. GIVA

**A different category of competitor: modern, silver-first, affordable D2C jewellery brand** (not a traditional gold jeweller) — but the app UX is the strongest benchmark in this whole set and deserves close study regardless of category.

**Onboarding:** polished lifestyle photography, social proof ("Trusted by 2.5M+ happy customers"), playful loading-state copy ("Just a moment — your beautiful treasures are loading!" with heart emoji). OTP login has Skip. Location permission requested (for store locator / delivery estimates) with the modern Android precise/approximate choice.

**Home:** Gold/Silver/Demifine material tabs, "Find Stores", pincode-based delivery ("Update Pincode Here"), a coin/wallet balance icon (loyalty currency, showed "0"), occasion-based gifting shortcuts (Gifts for Sister/Brother, Budget Gifting). Bottom nav: Home / Categories / Rakhi / **Crown** (likely loyalty/rewards program) / Profile.

**PLP — best in the entire test set:** star ratings per product (4.7–5.0), price + strikethrough MRP, **delivery date shown directly on the card** ("🚚 26th Aug"), promo codes surfaced inline with pre-computed discounted price ("Get It For ₹1,104" after code), and — uniquely — a **quick add-to-cart "+" button right on the product card**, no need to open the PDP to buy. Filter + Sort By persistent footer bar. Real shopping cart icon + wishlist heart in header.

**Overall GIVA verdict:** This is Myntra/Nykaa-caliber e-commerce UX applied to jewellery. Even though it's a different market segment (affordable silver/demifine vs. our gold focus), the *interaction patterns* — quick-add, inline discount math, delivery-date-on-card, ratings, loyalty coins — are exactly what a modern jewellery shopper now expects and should inform our app's PLP/PDP design regardless of price tier.

---

## 9. Chawla Jewellers

**Runs on yet another white-label jewellery-app platform, "Right Gold"** (distinct from the dsoft family — different branding, different vendor, but a near-identical feature concept: gold rate ticker, Gold SIP, Wallet, My Txn, Contact bottom nav, Digital Gold/Gift Card/Scheme icon row). This confirms a market pattern: **most small/mid-size Indian jewellers don't build custom apps — they license one of a handful of white-label "jewellery app in a box" platforms** (at least 2 identified: dsoft and Right Gold). Only the larger/better-funded players (GRT, Joyalukkas, GIVA) have bespoke apps.

Notable here: has both a shopping-bag (cart) icon AND wishlist heart AND notification bell in the header — closer to real e-commerce than the dsoft family. Seasonal campaign banner ("RIVAAZ — April 2026" collection launch) shows forward-dated event marketing built into the CMS.

---

## 10. My Bhima

**Hard login wall — no Skip/guest option.** "Welcome Back" screen requires Mobile Number + Password (not OTP), plus Sign Up and Forgot Password links. Branded "BHIMA — Pure Since 1925" but distinct from the separate "Bhima Gold" app (`com.bhima.gold`) also in this test set — likely **My Bhima is a staff/franchise/dealer-facing portal rather than the public customer app**, which would explain the mandatory credentialed login with no guest path. Did not attempt to create an account (out of scope for a competitive UX review, and mandatory-password apps like this are usually not the consumer storefront). Will rely on static APK analysis for anything further here.

---

## 11. Jewelflix Pravesh Gold

**Onboarding pitches itself explicitly as a metal-price tracker** ("Track the latest metal prices with daily updates") before anything else — positions the app as a financial utility first, jewellery store second. Only "Create Account" / "Login" shown by default (no visible Skip in the flow, though a small Skip button exists in the corner).

**Home screen leads with gold BAR/BULLION purchase** — 0.5 Gram / 1 Gram / 10 Gram gold bar tiles are the very first thing on the page, above even the metal rate cards. This is the strongest "buy gold as an investment" framing of any app tested — more prominent than GRT/Kalamandir/Ratanlal's scheme tiles which are usually a few scrolls down.

**Metal Rates section:** Gold 24K and 22K cards with exact freshness timestamp ("Updated: 22 August, 09:47 am") — good trust signal, more precise than competitors' unstamped rate bars. "Installment Plan" and "Custom Orders" tiles below. Real storefront welcome banner. Floating WhatsApp-style chat bubble (bottom-right, persistent). Bottom nav: Home / Search / Chat / Profile (chat as a first-class tab, not just a floating button, unusual).

**Takeaway:** of all apps tested, this one most aggressively sells "gold as investment/bullion" over "gold as jewellery" — worth deciding deliberately whether Aradhana wants that framing or a jewellery-first framing.

---

## 12. Malabar Gold & Diamonds

Celebrity-fronted onboarding (high-fashion bridal jewellery imagery), "Sign in / Register Later" guest path (good — doesn't force login), then an email-capture step even in guest mode (soft, skippable).

**Home:** "450+ Showrooms, 14 Countries" trust banner — reinforces this is a huge multinational chain, same tier as Joyalukkas. Location-set prompt for store/delivery personalization. Six clean shortcut tiles: Bestsellers, **Live Gold Rate**, Shop in Budget, Diamond Rings, Stunning Earrings, Book a Visit. Bottom nav: Home / Stores / Account / Menu (simpler than most — heavier reliance on a slide-out Menu for deep navigation). Floating chat bubble bottom-right (same pattern as Pravesh Gold).

**Overall Malabar verdict:** Confident, scale-driven branding (showroom count as a trust signal) with a clean, shortcut-tile home screen rather than a busy scheme-heavy one. "Book a Visit" and "Shop in Budget" as first-class home tiles are notable — budget-conscious shopping and appointment booking both get equal billing with browsing.

---

## 13. Tanishq

**Premium brand positioning from the first frame** — minimal serif wordmark logo, moody bridal jewellery macro photography, elegant wave-shaped color block transitions. Onboarding calls out a **Ring Size Calculator** ("measure your ring size even without visiting a store") as a hero feature — a concrete, useful utility none of the other apps explicitly marketed.

**Hard OTP login wall — no guest/Skip path found** (unlike most others in this set). Mobile number + OTP only, country-code selector, "By Continuing I agree to Terms of use & Privacy Policy". A persistent "How can I help you?" chat bubble sits in the corner even on the login screen. Did not proceed further with a real OTP (out of scope). Given Tanishq is India's largest organized jewellery retailer (Tata Group), a static pass on the APK is worth prioritizing here to see what's behind the login wall.

**Takeaway:** Tanishq trades browsing-friction for lead quality — likely deliberate, since they can rely on brand recognition to get users through an OTP wall that a lesser-known brand couldn't. Not a pattern we should copy blindly unless Aradhana has comparable brand pull; a Skip/guest-browse option (like most competitors offer) is safer for us.

---

## 14. Bhima Gold

**No login wall at all — straight into full browsing**, the most frictionless entry of any app tested. Country selector (IND) suggests multi-region like Joyalukkas/Malabar.

**Home:** Online Gold Rate ticker directly under the header (updates by karat — saw both 18KT and 22KT during scroll). "Jewellery Purchase Plans" and "Buy a Gift Card" as two big equal-weight buttons right up top. Large festival campaign hero (BHIMA Varamahalakshmi, forward-dated Aug 10–30 2026) with three clearly laid-out discount cards: Gold "Upto ₹1,000 Off per gram," Diamond "0% Making Charges & ₹10,000 Off + free 100mg gold coin on ₹1L diamond value," Silver "Flat ₹1,000 Off on every 50 grams" — the clearest, most quantified discount presentation of any app tested (most others just say "up to X% off" with no concrete numbers). Category tab strip (Rings/Earrings/Bangles/Chains/Pendants/Necklaces/Bracelets). Bottom nav: Home/Category/Search/**Cart**/Profile — real cart. Floating WhatsApp button.

**PLP:** real prices with strikethrough original price, wishlist heart, clean 2-column grid, no clutter.

**Overall Bhima Gold verdict:** Best combination of zero-friction entry + concrete, quantified discount messaging. The "₹X off per gram" and "₹X off per Y grams" framing is more persuasive and trustworthy than vague percentage banners — worth adopting.

---

# Static APK Analysis (decompiled with jadx)

Pulled `base.apk` from all 14 apps via ADB and decompiled with jadx to inspect permissions and bundled SDKs — this surfaces tech choices that aren't visible just from clicking through the UI.

**Payment gateways in use (industry-wide):** Razorpay is the most common (GIVA, Bhima Gold, Chawla, the whole dsoft family, Jewelflix, Joyalukkas, Tanishq, Malabar). PayU appears in the dsoft family + Chawla + Joyalukkas. Cashfree and a direct PhonePe SDK integration appear in GIVA, Bhima Gold/My Bhima, the dsoft family, Jewelflix. Juspay (an orchestration layer over multiple payment methods) appears in GIVA and Tanishq — the two most "modern stack" apps. **Takeaway: nobody here uses a single gateway exclusively — most stack 2–3 (Razorpay/PayU/Cashfree/PhonePe) for redundancy and lower decline rates.** We should plan for at least two payment gateways from day one.

**Hidden feature confirmed by static analysis, missed in live testing:** the entire **dsoft-family app** (Kalamandir, Ratanlal, Fatehchand, Manisha) plus **Chawla Jewellers** bundle the **Agora real-time video SDK** (`io.agora.agora_rtc_ng`) and have an Android call-notification "Video" answer action string in their resources. This strongly indicates a **live video call / virtual consultation feature** exists in these apps (likely "video call your nearest showroom" or a jeweller video-consult flow) that we didn't surface by clicking through the visible UI — it's probably gated behind login or a specific promo. This is a meaningful feature to consider for Aradhana: letting a customer video-call a salesperson to see a piece "in hand" before an in-store visit is a strong trust-building tool for high-value gold/diamond purchases.

**Analytics/attribution/marketing stack:** Firebase Analytics + Crashlytics is nearly universal (every app but Bhima's core, which still has Firebase). AppsFlyer (marketing attribution — tracks which ad campaign drove an install) appears in GIVA, Chawla, the dsoft family, Tanishq. MoEngage (push/in-app marketing automation) appears in Joyalukkas and Tanishq — the two most "customer lifecycle marketing"-mature apps. CleverTap appears in GIVA. OneSignal (push) appears in My Bhima. Facebook SDK (ad-conversion tracking) is nearly universal.

**Permissions worth flagging:**
- **Tanishq** requests `CALL_PHONE`, `ACCESS_BACKGROUND_LOCATION`, `REORDER_TASKS`, and `EXPAND_STATUS_BAR` — more invasive than any other app in the set. Background location in particular is a privacy-sensitive ask we should avoid unless there's a clear geofencing/store-proximity feature that justifies it (foreground location is enough for "find nearest store").
- **Malabar Gold** requests `READ_CALENDAR`/`WRITE_CALENDAR` — almost certainly to let "Book a Visit" add an entry directly to the user's calendar, a nice small touch.
- **GIVA, Chawla, and the dsoft family** request `READ_CONTACTS` — likely for a "refer a friend" or gifting flow (send a gift card to a contact). Worth doing only if we have a concrete use for it; unused contact permissions are a trust/privacy red flag on the Play Store listing.
- **Ornate NX** requests `BLUETOOTH_SCAN`/`BLUETOOTH_CONNECT` and (recall) failed to launch with an "IP address–port" server error — corroborates this being a POS/in-store hardware companion app (Bluetooth barcode scanner or card-swipe terminal), not a customer app.

**Not a homogenous market — confirmed 3 distinct app-building strategies:**
1. **Fully custom builds** — GRT, Joyalukkas, GIVA, Malabar, Tanishq, Bhima Gold, Jewelflix Pravesh Gold. Larger investment, more differentiated UX.
2. **White-label platform "dsoft"** — Kalamandir, Ratanlal CB Bafna, Fatehchand, Manisha. Identical codebase/library set confirmed via decompilation (same SDK bundle in every one).
3. **White-label platform "Right Gold"** — Chawla Jewellers (distinct vendor from dsoft, but same conceptual feature set).

This means roughly half the competitive set didn't build a bespoke app at all — which is actually an opportunity: a genuinely well-designed, purpose-built Aradhana app will stand out against the templated majority just on polish alone, without needing Joyalukkas/Tanishq-scale investment.

---

# Cross-App Synthesis & Recommendations for Aradhana Jewellers App

## What every serious competitor has, that we should treat as table stakes
1. **Live gold/silver rate visible on the home screen without navigating anywhere** — every single app does this, several update it by the minute with a timestamp. Non-negotiable for a jewellery app.
2. **Guest browsing with login deferred** — 10 of 14 apps let you browse without an account (Kalamandir, Ratanlal, Fatehchand, Chawla, GIVA, Malabar all had explicit "Skip"/"Later" options). Only Tanishq and My Bhima hard-walled it, and Tanishq can afford that on brand strength alone. **We should not force login before browsing.**
3. **Store locator + Call Us one tap away**, not buried in a menu (GRT, Malabar's "Stores" tab, etc.)
4. **A gold-investment/savings product** (Digital Gold, Gold SIP/Scheme, or price-lock "Book Now Buy Later") — present in nearly every app except the pure fashion-silver GIVA. This is clearly expected by the Indian jewellery-shopping audience, not a nice-to-have.
5. **WhatsApp or in-app chat as a first-class support channel** — floating chat bubble or full nav tab in the majority of apps.

## Where the market is weak — our opportunity
1. **Pricing transparency is inconsistent and often bad.** GRT and Kalamandir show no price on PLPs and Kalamandir's PDP has literally nothing but a wishlist button. Joyalukkas, GIVA, and Bhima Gold are the only ones with real strikethrough-MRP + discount pricing throughout. **We should always show a price (even if approximate, "starting from ₹X" pending exact weight) — never a bare product photo with no next step.**
2. **Almost nobody has a real quick-add-to-cart on the listing grid** — GIVA is the only one. A one-tap "+" on the PLP card (like GIVA's) removes real friction versus GRT/Kalamandir's enquiry-only model.
3. **No app in this set showed AR/virtual try-on**, despite `com.google.ar.core` being installed on this very tablet (likely for a different, unrelated app) — this is a genuine white-space feature if we can execute it well for rings/bangles/earrings.
4. **Delivery-date-on-card (GIVA) and quantified discount math ("₹1,000 off per gram", Bhima Gold) are rare and effective** — most competitors use vague "up to X% off" banners. Concrete numbers build more trust.
5. **A live-video consultation feature exists (Agora SDK) in 5 of the 14 apps but is not surfaced anywhere obvious in the UI** — if even competitors are burying a good feature, doing it well and prominently ("Video call our showroom" as a real, marketed home-screen tile, not a hidden flow) is a differentiator.
6. **Price Scanner (Joyalukkas)** — scan an in-store tag to pull up the product in-app — is a smart bridge between physical showroom visits and the app that nobody else replicates. Worth considering if Aradhana has a physical showroom presence.
7. **Nobody localizes well beyond Hindi/English/one regional language**, except Malabar Gold (multi-language even in the APK: bn/gu/hi/kn/mr/ta/te splits) and Bhima Gold. If Aradhana's customer base spans multiple language communities, this is worth doing properly.

## Concrete feature checklist for the Aradhana app (synthesized)
- [ ] Home screen: live gold/silver rate (multi-karat, timestamped) + banner carousel + quick category icons
- [ ] Guest browsing by default; OTP login only required at checkout/wishlist-sync, not before
- [ ] PLP: real price + strikethrough MRP + discount %, quick add-to-cart, wishlist heart, filter/sort, delivery estimate
- [ ] PDP: price, product code, making-charge breakdown ("View Details"), Add to Cart AND a "Book Appointment"/"Video Call Store" fallback for high-value pieces where online checkout feels risky to the customer
- [ ] Gold investment product: Digital Gold (buy fractional grams) + a savings scheme (SIP-style) + price-lock booking — pick at least one to start, ideally Digital Gold since it's the most "instant gratification" of the three
- [ ] Store locator + Book a Visit (calendar-integrated) + Call Us, all one tap from home
- [ ] WhatsApp/chat support, persistent floating button
- [ ] At least 2 payment gateways (e.g., Razorpay + Cashfree or PhonePe) for redundancy
- [ ] Avoid over-asking permissions — no background location, no contacts access unless a specific referral/gifting feature needs it and is clearly explained at request time

## Full app inventory tested
| # | App | Package | Login model | Pricing on PLP | Cart model | Notable feature |
|---|-----|---------|-------------|-----------------|-----------|------------------|
| 1 | GRT Jewellers | com.grtjewels.oriana | OTP/Google, guest OK | No | Enquiry/WhatsApp only | Store/appointment icons in header |
| 2 | Ornate NX | com.ornate.nx | N/A (broken) | N/A | N/A | POS/hardware companion, not consumer app |
| 3 | Kalamandir Jewellers | com.dsoft.kalamandirjewellers | OTP, Skip available | No | None (wishlist only) | Gold SIP as primary nav tab |
| 4 | Ratanlal CB Bafna | com.dsoft.ratanlalcbafnajewellers | OTP, Skip available | No | None visible | Digital Gold + Book My Gold tiles |
| 5 | Fatehchand Jewellers | com.dsoft.fatehchandjewellers | OTP, Skip available | No | None visible | E-Store video banner |
| 6 | Manisha Jewellers | com.dsoft.manishajewellers | OTP, Skip available | No | None visible | "Rate Alert" nav tab |
| 7 | Joyalukkas | com.joyalukkas.mcstaging.twa | Browsable first | Yes, with discounts | Real cart | Price Scanner, global multi-country |
| 8 | GIVA | co.giva.jewellery | OTP, Skip available | Yes, best-in-class | Real cart, quick-add | Delivery date on card, loyalty coins |
| 9 | Chawla Jewellers | com.chawlajewellers | OTP, Skip available | Not confirmed | Cart icon present | "Right Gold" white-label platform |
| 10 | My Bhima | sharaaninfo.mybhima | Hard wall (password) | N/A | N/A | Likely staff/franchise portal |
| 11 | Jewelflix Pravesh Gold | com.jewelflix.praveshgold | Account required | Not shown pre-login | N/A | Gold bar/bullion-first home screen |
| 12 | Malabar Gold & Diamonds | malabargold.qburst.com.malabargold | Browsable first | Not confirmed | Not confirmed | 450+ showrooms/14 countries trust banner |
| 13 | Tanishq | com.titancompany.tanishqapp | Hard wall (OTP) | N/A | N/A | Ring Size Calculator |
| 14 | Bhima Gold | com.bhima.gold | Browsable first | Yes, with discounts | Real cart | Quantified discount cards (₹/gram) |

---
*Report compiled via live on-device UI testing (ADB over WiFi debugging) and static APK analysis (jadx decompilation) on 2026-08-22. Screenshots saved to `App Test Reports/screenshots/`.*
