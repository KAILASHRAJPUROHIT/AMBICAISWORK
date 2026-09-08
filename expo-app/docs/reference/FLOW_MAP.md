# Joyalukkas Reference Audit — Navigation Flow Map

> Audit date: 2026-09-01
> Source: 18 manual screenshots + ADB captured screenshots
> Target: Aradhana Jewellers app replication

---

## App Structure Overview

```
App
├── Splash Screen (10-12s)
│   └── Home Screen (default tab)
│
├── Bottom Navigation (5 tabs)
│   ├── Home
│   ├── Price Scanner (full-screen)
│   ├── Category
│   ├── Gold Scheme (bottom sheet overlay)
│   └── Account
│
├── Search (from header)
│
├── Product Flow
│   ├── Product Listing (from Category or Home)
│   └── Product Detail (from Listing or Search)
│
├── Cart Flow
│   ├── Shopping Cart (from Product Detail or Header)
│   └── Checkout (Shipping → Payment)
│
└── Auth Flow
    ├── Login (from Account)
    └── Sign Up (from Login)
```

---

## Tab Navigation

### Bottom Nav Tabs (fixed at bottom)

| Tab | Icon | Default State | Active Indicator |
|-----|------|---------------|------------------|
| Home | House | First load | Red icon + label |
| Price Scanner | QR/Barcode | Tap to open | Full-screen camera |
| Category | 2x2 grid | Tap to navigate | Red icon + label |
| Gold Scheme | Coins | Tap to show sheet | Red icon + label |
| Account | Person | Tap to navigate | Red icon + label |

**Key behavior:**
- Tapping any tab (except Price Scanner) navigates to that screen
- Price Scanner opens a full-screen camera overlay
- Gold Scheme shows a bottom sheet overlay (not a full navigation)
- Bottom nav is hidden in: Price Scanner, Product Detail (replaced by Add to Cart bar)

---

## Screen-to-Screen Flows

### 1. Home Screen Flows

```
HOME SCREEN
    │
    ├── [Tap Search icon in header] → SEARCH SCREEN
    │
    ├── [Tap Cart icon in header] → SHOPPING CART
    │
    ├── [Tap category circle] → PRODUCT LISTING (filtered by category)
    │
    ├── [Tap hero banner] → PRODUCT LISTING or PROMO PAGE
    │
    ├── [Tap Price Scanner tab] → PRICE SCANNER (full-screen overlay)
    │
    ├── [Tap Category tab] → CATEGORY SCREEN
    │
    ├── [Tap Gold Scheme tab] → GOLD SCHEME (bottom sheet overlay)
    │
    └── [Tap Account tab] → ACCOUNT SCREEN
```

### 2. Category Screen Flows

```
CATEGORY SCREEN
    │
    ├── [Tap back arrow] → HOME (previous screen)
    │
    ├── [Tap "All Gold Jewellery" card] → PRODUCT LISTING (Gold Jewellery)
    │
    ├── [Tap "All Diamond Jewellery" card] → PRODUCT LISTING (Diamond Jewellery)
    │
    ├── [Tap "All Platinum Jewellery" card] → PRODUCT LISTING (Platinum Jewellery)
    │
    ├── [Tap "All Silver Jewellery" card] → PRODUCT LISTING (Silver Jewellery)
    │
    ├── [Tap category row item] → PRODUCT LISTING (filtered)
    │   ├── Earrings
    │   ├── Pendants
    │   ├── Rings
    │   ├── Nosepins
    │   ├── Bangles & Bracelets
    │   ├── Diamond Jewellery
    │   └── More Jewellery
    │
    ├── [Tap "Today's Gold Rate" card] → GOLD RATE SCREEN
    │
    ├── [Tap "Advance Booking" card] → BOOKING SCREEN
    │
    ├── [Tap "Buy Gift Card" card] → GIFT CARD SCREEN
    │
    ├── [Tap "Track Order" card] → ORDER TRACKING SCREEN
    │
    ├── [Tap "Store Locator" card] → STORE LOCATOR SCREEN
    │
    └── [Tap "Diamond Certificate" card] → CERTIFICATE SCREEN
```

### 3. Product Listing Flows

```
PRODUCT LISTING SCREEN
    │
    ├── [Tap back arrow] → CATEGORY or HOME (depending on entry point)
    │
    ├── [Tap Search icon] → SEARCH SCREEN
    │
    ├── [Tap Heart icon] → WISHLIST
    │
    ├── [Tap Cart icon] → SHOPPING CART
    │
    ├── [Tap sub-category circle] → PRODUCT LISTING (filtered)
    │
    ├── [Tap product card] → PRODUCT DETAIL
    │
    ├── [Tap SORT BY] → SORT MODAL
    │   └── Options: Position, Price (Low to High), Price (High to Low), Newest
    │
    ├── [Tap FILTER] → FILTER MODAL
    │   └── Options: Price range, Category, Metal, Weight, etc.
    │
    ├── [Tap price range pill] → FILTERED PRODUCT LISTING
    │
    └── [Scroll to bottom] → Load more products (pagination)
```

### 4. Product Detail Flows

```
PRODUCT DETAIL SCREEN
    │
    ├── [Tap back arrow] → PRODUCT LISTING (previous screen)
    │
    ├── [Tap Search icon] → SEARCH SCREEN
    │
    ├── [Tap Heart icon] → WISHLIST (toggle)
    │
    ├── [Tap Cart icon] → SHOPPING CART
    │
    ├── [Tap Video Call button] → VIDEO CALL (opens camera)
    │
    ├── [Tap Share icon] → SHARE SHEET (system)
    │
    ├── [Swipe image carousel] → Next/Previous product image
    │
    ├── [Tap "Price Breakup >"] → EXPAND PRICE BREAKUP TABLE
    │
    ├── [Tap "Product Details" accordion] → EXPAND PRODUCT DETAILS
    │
    ├── [Tap "Change Pincode"] → PINCODE INPUT MODAL
    │
    ├── [Tap "Write a Review"] → REVIEW FORM
    │
    ├── [Tap similar product card] → PRODUCT DETAIL (new product)
    │
    ├── [Tap Instagram photo] → INSTAGRAM (external link)
    │
    ├── [Tap "Need Help?"] → PHONE CALL or HELP SCREEN
    │
    ├── [Tap "Chat with us"] → CHAT SCREEN
    │
    ├── [Tap Heart icon (bottom bar)] → WISHLIST (toggle)
    │
    ├── [Tap Chat icon (bottom bar)] → CHAT SCREEN
    │
    └── [Tap "ADD TO CART" button] → SHOPPING CART (with toast notification)
```

### 5. Shopping Cart Flows

```
SHOPPING CART SCREEN
    │
    ├── [Tap back arrow] → PRODUCT DETAIL (previous screen)
    │
    ├── [Tap "-" button] → DECREMENT QUANTITY
    │
    ├── [Tap "+" button] → INCREMENT QUANTITY
    │
    ├── [Tap Heart icon] → MOVE TO WISHLIST
    │
    ├── [Tap Trash icon] → REMOVE FROM CART (with confirmation)
    │
    ├── [Toggle "Need Gift Wrap?"] → ENABLE/DISABLE GIFT WRAP
    │
    ├── [Tap "Have a Gift Card?"] → EXPAND GIFT CARD INPUT
    │
    ├── [Tap "Apply" coupon] → APPLY COUPON (validates code)
    │
    ├── [Tap "PROCEED TO CHECKOUT"] → CHECKOUT FLOW
    │   ├── Step 1: Cart (current)
    │   ├── Step 2: Shipping
    │   └── Step 3: Payment
    │
    └── [Tap Discover More cards] → SCHEME or GIFT CARD screens
```

### 6. Search Flows

```
SEARCH SCREEN
    │
    ├── [Tap back arrow] → HOME or PRODUCT LISTING (previous screen)
    │
    ├── [Type in search input] → SHOW POPULAR SEARCHES + SUGGESTED PRODUCTS
    │
    ├── [Tap popular search item] → PRODUCT LISTING (filtered by search term)
    │
    ├── [Tap suggested product] → PRODUCT DETAIL
    │
    └── [Tap Search button on keyboard] → PRODUCT LISTING (search results)
```

### 7. Account Screen Flows

```
ACCOUNT SCREEN (Guest State)
    │
    ├── [Tap back arrow] → HOME (previous screen)
    │
    ├── [Tap Search icon] → SEARCH SCREEN
    │
    ├── [Tap Heart icon] → WISHLIST
    │
    ├── [Tap Cart icon] → SHOPPING CART
    │
    ├── [Tap "Login" button] → LOGIN SCREEN
    │
    ├── [Tap "Profile"] → LOGIN SCREEN (requires auth)
    │
    ├── [Tap "My Orders"] → LOGIN SCREEN (requires auth)
    │
    ├── [Tap "My Cart"] → SHOPPING CART
    │
    ├── [Tap "Favourites"] → WISHLIST
    │
    ├── [Tap "My Returns"] → LOGIN SCREEN (requires auth)
    │
    └── [Tap "Jewellery Purchase Scheme"] → SCHEME SCREEN
```

### 8. Login Screen Flows

```
LOGIN SCREEN
    │
    ├── [Tap back arrow] → ACCOUNT SCREEN
    │
    ├── [Tap "Forgot Password"] → PASSWORD RESET FLOW
    │
    ├── [Tap "Terms & Conditions"] → TERMS PAGE
    │
    ├── [Tap "Privacy Policy"] → PRIVACY PAGE
    │
    ├── [Tap "Sign In" with valid credentials] → ACCOUNT SCREEN (logged in)
    │
    ├── [Tap "Sign In" with invalid credentials] → ERROR MESSAGE
    │
    └── [Tap "Sign Up"] → SIGN UP SCREEN
```

### 9. Price Scanner Flow

```
PRICE SCANNER (Full-screen overlay)
    │
    ├── [Tap X close button] → HOME (or previous screen)
    │
    ├── [Align QR/Barcode in frame] → SCAN RESULT
    │   └── Navigates to product or info page
    │
    └── [Press system back] → HOME (or previous screen)
```

### 10. Gold Scheme Flow

```
GOLD SCHEME (Bottom sheet overlay)
    │
    ├── [Tap outside sheet] → DISMISS (returns to Home)
    │
    ├── [Tap "Join Scheme"] → JOIN SCHEME FORM
    │
    ├── [Tap "Make Payments"] → PAYMENT SCREEN
    │
    ├── [Tap "Link Scheme"] → LINK SCHEME FORM
    │
    └── [Tap "Scheme Benefits"] → BENEFITS INFO PAGE
```

---

## Navigation Patterns

### Pattern 1: Tab Navigation
- Bottom nav is persistent across Home, Category, Account
- Tapping a tab replaces the main content area
- Bottom nav is HIDDEN in: Price Scanner, Product Detail

### Pattern 2: Stack Navigation
- Back arrow returns to previous screen
- Product flow: Category → Product Listing → Product Detail
- Cart flow: Product Detail → Cart → Checkout
- Search flow: Any screen → Search → Results → Product Detail

### Pattern 3: Modal/Overlay Navigation
- Price Scanner: Full-screen camera overlay
- Gold Scheme: Bottom sheet overlay
- Filter/Sort: Modal overlay (not captured, but standard pattern)
- Share: System share sheet

### Pattern 4: Push Navigation
- Product Detail pushes onto stack
- Cart pushes onto stack
- Checkout pushes onto stack (multi-step)

---

## Back Navigation Behavior

| Current Screen | Back Action | Destination |
|----------------|-------------|-------------|
| Home | System back | App exit |
| Category | Back arrow | Home |
| Product Listing | Back arrow | Category or Home |
| Product Detail | Back arrow | Product Listing |
| Shopping Cart | Back arrow | Product Detail |
| Search | Back arrow | Previous screen |
| Account | Back arrow | Home |
| Login | Back arrow | Account |
| Price Scanner | X button or system back | Previous screen |
| Gold Scheme | Tap outside sheet | Dismiss to Home |

---

## Auth-Gated Screens

The following screens require authentication:

| Screen | Auth Required | Redirect |
|--------|---------------|----------|
| Profile | Yes | Login |
| My Orders | Yes | Login |
| My Returns | Yes | Login |
| Checkout (Shipping/Payment) | Yes | Login |
| Write a Review | Yes | Login |
| Wishlist (view saved items) | Yes | Login |
| Jewellery Purchase Scheme | Partial | Login for full access |

---

## Deep Link Targets

| URL Pattern | Screen | Notes |
|-------------|--------|-------|
| `/:category` | Product Listing | Category filtered |
| `/product/:id` | Product Detail | Direct product access |
| `/cart` | Shopping Cart | Direct cart access |
| `/search?q=:query` | Search Results | Pre-filled search |
| `/account` | Account Screen | Account landing |
| `/login` | Login Screen | Auth landing |
| `/gold-scheme` | Gold Scheme | Scheme landing |
| `/price-scanner` | Price Scanner | Scanner overlay |

---

## Loading States

| Screen | Loading State | Notes |
|--------|---------------|-------|
| Home | Skeleton loader | Category circles + banner placeholder |
| Product Listing | Skeleton cards | 2-col grid placeholder |
| Product Detail | Skeleton layout | Image + info placeholder |
| Search | Spinner | Below search input |
| Cart | Skeleton items | Cart item placeholders |
| Category | Skeleton rows | Category list placeholder |
