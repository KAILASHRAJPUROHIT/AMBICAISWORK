# Joyalukkas Reference Audit — Screen Map

> Audit date: 2026-08-31
> Device: Redmi Tab (2509BRP2DI), 192.168.0.18:5555
> App: `com.joyalukkas.mcstaging.twa` (TWA — Trusted Web Activity)

---

## Home Screen

### Header (sticky, white background)

| Left | Right |
|------|-------|
| Joyalukkas logo (golden heart icon + "Joyalukkas" text) | Country selector ("India" with flag icon + dropdown arrow) |
| Tagline: "World's favourite jeweller" (smaller text below logo) | Search icon (magnifying glass, outline) |
| | Cart/bag icon (outline) |

- **Background:** White `#FFFFFF`
- **Logo size:** ~140×40px visual
- **Tagline:** ~10px, gray or muted tone
- **Right icons:** ~24px, dark/black outline

### Category Carousel (horizontal scroll, immediately below header)

- **Layout:** Horizontal `ScrollView` (not flatlist), items visible ~8.5 at a time
- **Item shape:** Circular (~80px diameter circle) with light peach/salmon background `~#F5E6E0`
- **Label below circle:** Centered text, ~11px, black/dark gray
- **Categories observed (left to right):**
  1. Express Delivery (truck icon on maroon/red circle)
  2. Gift Card (gold gift card icon)
  3. New Arrivals (jewelry piece on peach background)
  4. Wedding (green necklace on peach background)
  5. Kids (gold pendant/charm on peach background)
  6. Platinum (silver bracelet on peach background)
  7. Men's Collection (multi-gem ring on peach background)
  8. Silver (silver ring with emeralds on peach background)
  9. Bullions (gold bars on peach background)
- **Carousel border/outline:** Each circle has a thin orange/copper border `~#C87941`
- **Container:** Full-width horizontal scroll, ~170px height including labels
- **No arrow buttons** — pure swipe scroll

### Hero Banner (full-width, auto-scrolling carousel)

- **Position:** Below category carousel, above bottom nav
- **Height:** ~55–60% of viewport (~400px on this tablet, ~350px on phone)
- **Edge-to-edge:** Yes, full bleed left and right (no margins)
- **Border radius:** 0 (square/rectangle)
- **Behavior:** Auto-scrolling carousel, smooth transitions
- **Observed slides:**
  1. **Dark slide:** Black/dark background with Joyalukkas logo in white (golden heart + white text). Cinematic, blurred background elements.
  2. **Gold ribbon slide:** Warm golden/cream background with a flowing gold ribbon graphic. Luxurious, elegant feel.
  3. **Sale promo slide:** "THE BIGGEST JEWELLERY SALE OF THE YEAR" — large red/maroon serif text, "Incredible Flat" in italic gold on red banner, model photo on right. Background: cream with subtle damask/floral pattern.
- **No dot indicators** visible (may be hidden or below fold)
- **Transition:** Slides from right to left, smooth animation

### Bottom Navigation Bar (fixed at bottom)

- **Background:** Light peach/salmon `~#FDF0EC` or `~#F9E8E2`
- **Height:** ~70px (including labels)
- **Icon style:** Outline (inactive), filled or colored (active)
- **Active color:** Red/crimson `~#D42426` (Home tab active)
- **Inactive color:** Dark gray/black outline `~#333333`
- **Label text:** ~10px, below each icon
- **Tabs (5 total):**
  1. **Home** — house icon (active state = filled red)
  2. **Price Scanner** — barcode/QR scanner icon
  3. **Category** — 2×2 grid icon
  4. **Gold Scheme** — coins/stacked coins icon
  5. **Account** — person/user icon

### Overall Home Screen Flow (top to bottom)

```
┌─────────────────────────────────────────────┐
│ HEADER (logo + tagline | country + search + cart) │
├─────────────────────────────────────────────┤
│ CATEGORY CAROUSEL (horizontal scroll, circular items)  │
├─────────────────────────────────────────────┤
│                                             │
│           HERO BANNER CAROUSEL              │
│         (full width, auto-scroll)           │
│                                             │
├─────────────────────────────────────────────┤
│ BOTTOM NAV: Home | Price Scanner | Category │ Gold Scheme | Account │
└─────────────────────────────────────────────┘
```

**Key observation:** The home screen is SHORT — it shows only the category carousel and the hero banner. No additional content sections below the hero banner before the bottom nav. The bottom nav takes up fixed space at the bottom.

---

## Category Screen

### Header
- White background, black text
- Back arrow (←) on left
- "Categories" title
- No search/cart icons in this header

### Category Cards (2×2 grid at top)
- 4 large cards with rounded corners, pink/mauve background `~#D4637A`
- Each card shows a product image + label text below
- Cards observed:
  1. All Gold Jewellery (gold necklace image)
  2. All Diamond Jewellery (diamond earrings image)
  3. All Platinum Jewellery (platinum chain image)
  4. All Silver Jewellery (silver pendant image)

### Category List (scrollable rows below cards)
- Rows with peach/light background `~#FDF0EC`
- Each row: Text on left, chevron (›) on right
- Thin border/separator between rows
- Categories observed:
  1. Earrings
  2. Pendants
  3. Rings
  4. Nosepins
  5. Bangles & Bracelets
  6. Diamond Jewellery
  7. More Jewellery

### Quick Access Cards (below category list, 3-column grid)
- 2 rows × 3 columns of cards
- Each card: red icon + title (red text) + description (gray text)
- Cards observed:
  1. **Today's Gold Rate** — "Check the prevailing gold rates in both retail and online stores."
  2. **Advance Booking** — "Book Jewellery by paying an advance."
  3. **Buy Gift Card** — "Surprise someone with the perfect pick."
  4. **Track Order** — "Because every precious moment deserves tracking."
  5. **Store Locator** — "Discove the brilliance near you find our jewellery stores"
  6. **Diamond Certificate** — "Your guarantee of diamond excellence."

---

## Account Screen

### Header
- White background, black text
- Back arrow (←) on left
- "My Account" title
- Right side: Search icon, Heart/Wishlist icon, Cart/bag icon

### User Section (peach background)
- Large orange/peach circular avatar with initial letter "G"
- "Hey, 👋 Guest" text (with waving hand emoji)
- "Login" button — red outline border, red text, right-aligned

### Menu Items (list with icons)
- Each row: Icon (outline) + Text label
- Separated by thin pink/peach divider lines
- Items:
  1. Profile (person outline icon)
  2. My Orders (delivery truck icon)
  3. My Cart (bag icon)
  4. Favourites/Wishlist (heart outline icon)
  5. My Returns (refresh/circle icon)
  6. Jewellery Purchase Scheme (document/bill icon)

---

## Price Scanner Screen

### Full-screen camera scanner
- **Background:** Black `#000000` (camera viewfinder)
- **Header:** No traditional header — close button (X) in top-right corner
  - White circle outline with white X inside
- **Scan frame:** Green corner brackets at 4 corners forming a rectangular scan area
  - Corner bracket color: Bright green `~#00FF00`
  - Brackets are small L-shaped corners
- **Scan line:** Horizontal red line across the middle of the scan area
  - Color: Red `~#FF0000`
  - Animated (moves up and down)
- **Bottom text:** "Align QR/Barcode within the frame"
  - White text, centered, ~14px
- **Bottom nav:** Hidden (full-screen mode)
- **No bottom nav visible** — scanner takes full screen

### Close behavior
- Tapping X returns to previous screen (Home or last tab)

---

## Gold Scheme Screen

### Bottom Sheet Overlay (not a full screen)
- **Trigger:** Tapping "Gold Scheme" tab in bottom nav
- **Behavior:** Bottom sheet slides up from bottom, overlaying the current screen (Home)
- **Background:** Current screen (Home) visible behind, dimmed
- **Video/animation visible** behind the sheet — someone sketching jewelry

### Bottom Sheet Content
- **Background:** Light peach `~#FDF0EC`
- **Rounded top corners** (~16px radius)
- **2×2 grid of action cards:**

| Card | Icon | Text |
|------|------|------|
| 1 | Sparkle/stars icon (orange) | Join Scheme |
| 2 | Hand with rupee icon (orange) | Make Payments |
| 3 | Link chain icon (orange) | Link Scheme |
| 4 | Percentage badge icon (orange) | Scheme Benefits |

- **Card style:** White background, thin border, rounded corners (~12px)
- **Icon + text layout:** Icon on left, text on right, vertically centered
- **Text color:** Dark/black `~#1A1A1A`
- **Icon color:** Orange `~#C87941` or similar
- **Padding:** ~16px between cards
- **Sheet height:** ~40% of screen

---

## Login Screen

### Header Section (top 40%)
- **Background:** Large hero image of ornate jewelry (gold necklace with intricate details)
- **Back arrow:** White left arrow in top-left corner
- **No other header elements**

### Form Section (bottom 60%)
- **Background:** White `#FFFFFF`
- **Rounded top corners** (~20px radius) overlapping the hero image
- **Title:** "Welcome back to **Joyalukkas**"
  - "Welcome back to" — dark/black, ~20px, regular weight
  - "Joyalukkas" — red `~#D42426`, ~20px, bold/semibold
  - Centered

### Form Fields
- **Email/Phone field:**
  - Label: "Email/ Phone" — dark gray, ~12px
  - Input: Rounded border `~#E0E0E0`, ~48px height
  - Placeholder: "Enter Email/Phone" — light gray
- **Password field:**
  - Label: "Password" (left) + "Forgot Password" (right, red text `~#D42426`)
  - Input: Same rounded border style
  - Placeholder: "Password*"
  - Eye icon (visibility toggle) on right side

### Terms Text
- "By continuing, you agree to the Joyalukkas **Terms & Conditions** and **Privacy Policy**"
- Links in red `~#D42426`
- ~12px, gray base color

### Sign In Button
- Full-width red button `~#D42426`
- White text "Sign In", ~16px, bold
- Rounded corners (~8px)
- ~50px height

### Sign Up Link
- "Don't you have an account? **Sign Up**"
- Centered, "Sign Up" in red `~#D42426`
- ~14px

---

## Search Screen

### Header
- White background
- Back arrow (←) on left
- "Search" title text

### Search Input
- **Input field:** Full-width with orange/coral border `~#C87941`
- **Left icon:** Magnifying glass (gray)
- **Placeholder:** "Search"
- **Background:** White
- **Rounded corners** (~8px)
- **Keyboard:** Auto-opens on screen load

### Search Results (when typing)
- **Background:** Light peach `~#FDF0EC` below search field
- **Popular Searches section:**
  - Header: "Popular Searches" — black, ~16px, bold
  - List items with clock icon (history):
    - "Gold neckl in Jewellery"
    - "Gold neckl in Category"
    - "Gold neckl in Shop By Gender"
    - "Gold neckl in Women's Jewellery"
  - Each item: ~14px, dark gray, separated by thin lines

### Suggested Products (horizontal scroll)
- **Header:** "Suggested Products" — black, ~16px, bold
- **Horizontal scroll** of product cards (same style as product listing)
- Each card:
  - Product image on white/light background
  - Badge (e.g., "Best Seller" pink badge, "Express Delivery" green badge)
  - Heart icon (wishlist) top-right
  - Product name below image
  - Price below name

---

## Product Listing Screen

### Header
- White background
- Back arrow (←) on left
- Category name (e.g., "Gold Jewellery") — black, ~16px
- Right side: Search icon, Heart/Wishlist icon, Cart/bag icon

### Category Banner (top)
- **Full-width hero image** — large product photo (e.g., ornate necklace on purple background)
- **Rounded corners** (~12px)
- **Height:** ~300px
- **Below banner:** Horizontal scroll of sub-category circles (same style as home page)

### Sub-Category Carousel (below banner)
- **Horizontal scroll** of circular items
- Same style as home page: circular images with peach background, copper border
- Categories: Nosepin, Bangles & Bracelets, Jewellery Set, Mangalsutra, etc.

### Product Count Bar
- "Gold Jewellery" title — black, ~16px, bold
- "3250 Designs" — gray, ~12px

### Product Grid (2 columns)
- **Column gap:** ~12px
- **Card style:** White background, slight shadow/rounded corners

### Product Card
- **Image area:** Square (~160px), white/light background
  - Share icon (bottom-right of image area)
  - Heart/wishlist icon (top-right corner)
  - Badge (top-left, if applicable):
    - "New" — teal/green badge `~#5CBFB5`
    - "Express Delivery" — green badge with truck icon
    - "Best Seller" — pink/rose badge
- **Below image:**
  - Current price: Black, ~16px, bold (e.g., "₹38,916")
  - Original price: Gray, strikethrough, ~14px (e.g., "₹42,062")
  - Discount: Red text `~#D42426`, ~12px (e.g., "40% Off on Making Value")
  - Product name: Dark/black, ~14px, regular weight

### Filter Section (scrollable)
- **"Filter By Price"** section with horizontal scroll of pill buttons:
  - "Under 10k", "10k - 15k", "15k - 20k", "20k - 30k"
  - "30k - 40k", "40k - 50k", "50k - 75k", "75k - 100k"
  - **Pill style:** White background, thin gray border, rounded, ~14px text
  - **Selected state:** Not observed (none selected in screenshots)

### Bottom Bar (fixed)
- **Left:** "SORT BY" with icon + "Position" label
- **Center:** Grid view / List view toggle (grid active = red icon)
- **Right:** "FILTER" with icon + "Not applied" label
- **Background:** White
- **Height:** ~56px

### Pagination
- "Showing 12/3250 Designs" — centered, gray text, ~12px
- Up arrow icon (^) for scroll-to-top

---

## Product Detail Screen

### Header (sticky)
- White background
- Back arrow (←) on left
- Product name — black, ~14px, single line (e.g., "Halo Dot Gold Earrings")
- Right side: Search icon, Heart/Wishlist icon, Cart/bag icon

### Product Image Carousel (top 50% of screen)
- **Full-width** product image
- **White/light background**
- **Dot indicators** below image (red active, gray inactive) — 6 dots
- **Share icon** (bottom-right of image area)
- **Video Call button** (bottom-left of image area):
  - Red circle with video camera icon
  - "Video Call" text in pill badge

### Product Info Section
- **Product name:** Black, ~18px, bold
- **SKU:** Gray, ~12px (e.g., "ECM110001281")
- **Price row:**
  - Current price: Black, ~20px, bold (e.g., "₹65,650")
  - Original price: Gray, strikethrough, ~16px (e.g., "₹71,033.00")
  - "Price Breakup >" link on right (red text)
- **Tax note:** "(MRP Inclusive of all taxes)" — gray, ~12px
- **Discount:** "40% Off on Making Value" — red text `~#D42426`, ~14px
- **Availability:**
  - Green truck icon + "Ready to dispatch" (green text)
  - OR red clock icon + "Made to Order" (gray text) with info icon

### Discover More Section (2-column cards)
- **Left card:** "Join Easy Gold Scheme! Start with Rs. 1000. 18% off on gold making charge"
  - Sparkle icon, orange text
- **Right card:** "Get instant 2% discount with Joyalukkas egift cards! Perfect for every occasion."
  - Gift card icon, orange text
- **Card style:** Light peach background, rounded corners

### Check Delivery Date
- **Section header:** "Check Delivery Date" — black, ~16px
- **Pincode input:** Location pin icon + "401504" + "Change Pincode" link (red)
  - Border, rounded, ~48px height
- **Delivery info:**
  - "Free Delivery By : Sep 5, 2026" — green text
  - "14 Days Return" — gray text with info icon

### Trust Badges (4-column)
- Icons with labels below:
  1. Easy Exchange (refresh icon)
  2. Certified Jewellery (checkmark icon)
  3. Lifetime Product Service (handshake icon)
  4. 14 Days Easy Return (refresh icon)
- All icons: Orange/coral `~#C87941`
- Separated by thin vertical lines

### Product Details (accordion)
- "Product Details" — black, ~16px, with chevron down icon
- Expandable section (collapsed in screenshots)

### Price Breakup (accordion, expanded)
- "Price Breakup" — black, ~16px, with chevron up icon
- **Table layout:**

| Component | Rate | Weight | Discount | Value |
|-----------|------|--------|----------|-------|
| Metal (Base) | - | - | - | ₹54,447.22 |
| Gold | 14385/Gram (22 KT) | 3.785 Gram | - | - |
| Stone | - | - | - | ₹1,450.00 |
| Colour Stone 1 No(s) | - | 0.58 g | - | - |
| Making Charges (40% Off) | - | - | ₹5,226.93 | ₹7,840.40 |
| Sub Total | - | - | - | ₹63,737.63 |
| Tax (Gst) (3%) | - | - | - | ₹1,912.13 |
| **Grand Total** | - | - | **₹5,226.93** | **₹65,650.00** |

- Component names: Red/coral text `~#D42426`
- Values: Dark text, right-aligned
- Table background: Light peach `~#FDF0EC`

### Product Description
- "Product Description" header — dark, ~16px
- Description text: Gray, ~14px, multi-line
- **Brand story section:**
  - "CRAFTING Legacy" — stylized text (cursive "Legacy")
  - Brand imagery (ring sketch, jewelry photo)
  - Brand description text

### Reviews Section
- "Real Stories, Real Feedback" — dark, ~16px
- **Rating summary:**
  - "0/5.0" — large red text
  - "0 reviews" — gray
  - 5 empty stars
  - "Write a Review" — red button
- **Rating bars:** 5 Star through 1 Star with horizontal progress bars (all empty)

### Similar Products (horizontal scroll)
- "Similar Products" header — dark, ~16px
- Horizontal scroll of product cards (same style as listing)
- Cards show: image, "New" badge, heart icon, product name, price

### Instagram Section
- "Sneak peeks on Instagram" + Instagram icon
- 2-column grid of Instagram lifestyle photos
- Photos show jewelry being worn/displayed

### Need Help / Chat
- **Two buttons side-by-side:**
  - "Need Help?" — phone icon, peach background
  - "Chat with us" — chat icon, peach background
- **Button style:** Rounded, ~48px height, light peach background

### Sticky Bottom Bar (fixed at bottom)
- **Left:** Heart icon (wishlist) — orange/gold background, white heart
- **Middle:** Chat icon — white background, red border, red icon
- **Right:** "ADD TO CART" button — red `~#D42426`, white text, full-width minus the two icons
  - Lock/bag icon before text
  - Rounded corners

---

## Shopping Cart Screen

### Header
- White background
- Back arrow (←) on left
- "Shopping Cart" — black, ~16px

### Progress Stepper (top)
- 3 steps: **Cart** → **Shipping** → **Payment**
- Active step: Green circle + green line
- Inactive: Gray circle + gray line
- Step labels below circles

### Discover More Cards (same as product detail)
- "Join Easy Gold Scheme!" card
- "Get instant 2% discount with gift cards" card

### Cart Items
- **"Cart (1 item)"** — black, ~16px, bold
- **Item card:**
  - Product image (square, ~100px)
  - Product name — black, ~14px
  - Price — black, ~16px (e.g., "₹65,650.00")
  - Quantity controls: minus(-) | count | plus(+)
    - Rounded pill, gray border
  - Heart icon (move to wishlist)
  - Trash icon (delete)

### Gift Options
- **"Need Gift Wrap?"** — toggle switch (peach background)
  - Gift wrap icon + text + toggle
- **"Have a Gift Card?"** — expandable row
  - Gift card icon + text + right chevron

### Coupon Section
- **Input field:** "Enter Coupon Code" — rounded, gray border
- **"Apply" button** — red, rounded

### Order Summary
- **Subtotal:** Right-aligned, ₹65,650
- **Gift wrapper charges:** Right-aligned, ₹0
- **Total:** Right-aligned, ₹65,650 (bold)
- "(Inclusive of all taxes)" — gray, ~12px

### Sticky Bottom Bar
- **Left:** "Total (1 item)" + "₹65,650" — bold
- **Right:** "PROCEED TO CHECKOUT" — red button, white text, rounded

### Toast Notification
- "Item added to cart." — green checkmark + text
- Appears briefly at bottom

---

## Screens Still Not Captured

- [ ] **Wishlist** — saved items view
- [ ] **Account - logged in state** — profile view after login
- [ ] **Checkout flow** — shipping + payment steps
- [ ] **Store locator** — if accessible
- [ ] **Country selector dropdown** — from header
- [ ] **Filter/sort modal** — full filter panel within product listing

---

## Splash Sequence (from previous capture)

| Time | Event | Notes |
|------|-------|-------|
| 0s | Native splash (red background) | 35KB screenshot |
| 1s | Still splash | 35KB |
| 2s | White loading screen | TWA Chrome loading, 186KB |
| 4s | Still loading | 191KB |
| 7s | Splash with red background + interlocking rings logo | 1.1MB |
| 12s | Home screen fully loaded | 1.3MB |

**Total splash time:** ~10–12 seconds (slow, TWA overhead)

---

## Design Tokens (observed)

| Token | Value | Notes |
|-------|-------|-------|
| `COLOR_PRIMARY` | `~#D42426` | Red/crimson, active tab, buttons |
| `COLOR_PRIMARY_LIGHT` | `~#E8574D` | Lighter red for secondary buttons |
| `COLOR_BG` | `#FFFFFF` | White, header, cards |
| `COLOR_BG_BOTTOM_NAV` | `~#FDF0EC` | Light peach, bottom nav |
| `COLOR_BG_CATEGORY` | `~#F5E6E0` | Peach/salmon circles |
| `COLOR_BG_CARD` | `#FFFFFF` | White, product cards |
| `COLOR_BG_INPUT` | `#FFFFFF` | White, form fields |
| `COLOR_BG_BADGE_NEW` | `~#5CBFB5` | Teal/green, "New" badge |
| `COLOR_BG_BADGE_EXPRESS` | `~#4CAF50` | Green, "Express Delivery" badge |
| `COLOR_BG_BADGE_BESTSELLER` | `~#E8A0B0` | Pink, "Best Seller" badge |
| `COLOR_BORDER_CATEGORY` | `~#C87941` | Orange/copper circle border |
| `COLOR_BORDER_INPUT` | `~#E0E0E0` | Light gray, form field borders |
| `COLOR_BORDER_CARD` | `~#E8E8E8` | Very light gray, card borders |
| `COLOR_SCANNER_GREEN` | `~#00FF00` | Bright green, QR scanner corners |
| `COLOR_SCANNER_RED` | `~#FF0000` | Red, scanner line |
| `COLOR_TEXT_PRIMARY` | `~#1A1A1A` | Near black, headings |
| `COLOR_TEXT_SECONDARY` | `~#666666` | Gray, taglines, descriptions |
| `COLOR_TEXT_ACTIVE` | `~#D42426` | Red, active tab label |
| `COLOR_TEXT_INACTIVE` | `~#333333` | Dark gray, inactive tab |
| `COLOR_TEXT_DISCOUNT` | `~#D42426` | Red, discount percentage |
| `COLOR_TEXT_LINK` | `~#D42426` | Red, clickable links |
| `COLOR_TEXT_DELIVERY` | `~#4CAF50` | Green, delivery date text |
| `COLOR_TEXT_ORANGE` | `~#C87941` | Orange, scheme/trust badges |
| `COLOR_TEXT_STRIKETHROUGH` | `~#999999` | Gray, original prices |
| `FONT_LOGO` | Custom/Joyalukkas brand | Logo has golden heart + serif text |
| `FONT_TAGLINE` | ~10px | Smaller, secondary color |
| `FONT_CATEGORY_LABEL` | ~11px | Below circular icons |
| `FONT_BOTTOM_NAV` | ~10px | Below icons |
| `FONT_PRODUCT_NAME` | ~14px | Product card names |
| `FONT_PRODUCT_PRICE` | ~16px, bold | Product card current price |
| `FONT_PRODUCT_ORIGINAL` | ~14px, strikethrough | Product card original price |
| `FONT_SECTION_HEADER` | ~16px, bold | Section headings |
| `FONT_FORM_LABEL` | ~12px | Form field labels |
| `FONT_FORM_INPUT` | ~14px | Form field input text |
| `FONT_BUTTON_TEXT` | ~16px, bold | Button labels |
| `FONT_SMALL_NOTE` | ~12px | Tax notes, disclaimers |

---

## Comparison with Aradhana Current State

| Element | Joyalukkas Reference | Aradhana Current | Status |
|---------|---------------------|-------------------|--------|
| Header logo | Left-aligned, brand + tagline | Header exists | Review needed |
| Country selector | Right side, flag + dropdown | N/A | New feature |
| Search icon | Outline magnifying glass | Exists (different style) | Restyle |
| Cart icon | Outline bag | Exists | Restyle |
| Category carousel | Circular items, peach bg, copper border | 3D carousel, square items | **MUST REWRITE** |
| Hero banner | Full-width, auto-scroll, ~55% height | 3D hero with translateZ | **MUST REWRITE** |
| Bottom nav | 5 tabs: Home, Price Scanner, Category, Gold Scheme, Account | Different tab set | **REDESIGN** |
| Bottom nav style | Peach bg, red active, outline icons | Different style | **REDESIGN** |
| Background color | White top, peach bottom nav | Varies | **MUST UPDATE** |
| Splash | Red bg → logo → 10–12s load | Video splash attempt | **REDESIGN** |
| Price Scanner | Full-screen camera QR scanner | N/A | **NEW FEATURE** |
| Gold Scheme | Bottom sheet with 4 action cards | N/A | **NEW FEATURE** |
| Search | Dedicated screen with Popular Searches + Suggested Products | Different style | **REDESIGN** |
| Product listing | 2-col grid, filter pills, category carousel, sub-categories | Different layout | **REDESIGN** |
| Product detail | Image carousel, Video Call, Price Breakup table, trust badges, reviews, similar | Different layout | **REDESIGN** |
| Cart | Progress stepper, gift wrap, coupon, checkout | Different layout | **REDESIGN** |
| Login | Email/password, hero image, Sign In/Sign Up | Different flow | **REDESIGN** |
| Category screen | 4 cards (Gold/Diamond/Platinum/Silver) + 7 scrollable rows + 6 quick-access | Different layout | **REDESIGN** |
| Account screen | Avatar + 6 menu items | Different layout | **REDESIGN** |
