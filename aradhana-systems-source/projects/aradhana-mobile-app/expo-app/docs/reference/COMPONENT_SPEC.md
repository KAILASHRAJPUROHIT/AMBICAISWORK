# Joyalukkas Reference Audit — Component Spec

> Audit date: 2026-09-01
> Source: 18 manual screenshots from Joyalukkas TWA app
> Target: Aradhana Jewellers app replication

---

## Global Dimensions

| Component | Dimension | Notes |
|-----------|-----------|-------|
| Screen width (tablet) | 1280px | Redmi Tab |
| Screen height (tablet) | 800px | Redmi Tab |
| Status bar height | ~24px | System |
| Bottom nav height | ~70px | Including labels |
| Header height | ~56px | Standard header |
| Safe area bottom | ~20px | Android nav bar |

---

## Colors

### Primary Palette

| Name | Hex | Usage |
|------|-----|-------|
| Red Primary | `#D42426` | Active tabs, buttons, links, prices |
| Orange Accent | `#C87941` | Category borders, scheme icons, trust badges |
| Teal Badge | `#5CBFB5` | "New" product badge |
| Green Delivery | `#4CAF50` | Delivery date, "Ready to dispatch" |
| Pink Badge | `#E8A0B0` | "Best Seller" badge |

### Background Colors

| Name | Hex | Usage |
|------|-----|-------|
| White | `#FFFFFF` | Headers, cards, inputs, product detail bg |
| Light Peach | `#FDF0EC` | Bottom nav, cart bg, price breakup bg |
| Peach Category | `#F5E6E0` | Category circles bg |
| Black | `#000000` | Price scanner bg |
| Dark Overlay | `rgba(0,0,0,0.5)` | Modal overlays |

### Text Colors

| Name | Hex | Usage |
|------|-----|-------|
| Near Black | `#1A1A1A` | Headings, product names |
| Dark Gray | `#333333` | Inactive nav labels, body text |
| Medium Gray | `#666666` | Taglines, descriptions |
| Light Gray | `#999999` | Original prices, strikethrough |
| Placeholder Gray | `#CCCCCC` | Input placeholders |

---

## Typography Scale

| Token | Size | Weight | Usage |
|-------|------|--------|-------|
| H1 | 20px | Bold | Page titles, product detail name |
| H2 | 18px | Bold | Product detail name |
| H3 | 16px | Bold | Section headers, button text |
| Body | 14px | Regular | Product names, form input, body text |
| Small | 12px | Regular | Labels, notes, disclaimers |
| Tiny | 10px | Regular | Bottom nav labels, tagline |

---

## Component Specifications

### 1. Bottom Navigation Bar

```
Height: 70px
Background: #FDF0EC (light peach)
Border: None (clean edge)
Padding: 8px 0 12px 0

Tab item:
  Width: 20% (5 tabs)
  Icon size: 24px
  Icon style: Outline (inactive), Filled (active)
  Icon color inactive: #333333
  Icon color active: #D42426
  Label size: 10px
  Label color inactive: #333333
  Label color active: #D42426
  Gap between icon/label: 4px

Tabs (left to right):
  1. Home (house icon)
  2. Price Scanner (barcode/QR icon)
  3. Category (2x2 grid icon)
  4. Gold Scheme (coins icon)
  5. Account (person icon)
```

### 2. Header Bar

```
Height: 56px
Background: #FFFFFF
Border-bottom: 1px solid #F0F0F0

Left section:
  Back arrow: 24px, #333333 (optional, not on Home)
  Title: 16px, #1A1A1A, bold

Right section:
  Icon buttons: 24px each
  Icons: Search, Heart/Wishlist, Cart/Bag
  Color: #333333
  Gap: 16px between icons
```

### 3. Category Circle Item (Home Carousel)

```
Container:
  Width: 80px
  Height: 80px (circle)
  Border: 2px solid #C87941
  Background: #F5E6E0 (peach)
  Border-radius: 50%

Image:
  Width: 60px
  Height: 60px
  Border-radius: 50%
  Centered in container

Label:
  Font-size: 11px
  Color: #1A1A1A
  Text-align: center
  Margin-top: 6px
  Max-width: 80px
  Overflow: ellipsis

Horizontal scroll:
  Padding: 0 16px
  Gap: 12px between items
  Shows ~8.5 items at a time
  Scroll snap: None (free scroll)
```

### 4. Hero Banner (Home)

```
Width: 100% (edge-to-edge)
Height: ~55% of viewport (~400px tablet, ~350px phone)
Border-radius: 0
Auto-scroll: Yes, smooth transition
Interval: ~5 seconds
Dot indicators: Not visible

Slides observed:
  1. Dark bg + Joyalukkas logo (white)
  2. Gold ribbon on warm bg
  3. Sale promo with model
```

### 5. Product Card (Listing/Grid)

```
Container:
  Width: ~48% (2-column grid)
  Background: #FFFFFF
  Border-radius: 8px
  Overflow: hidden
  Gap between columns: 12px

Image area:
  Width: 100%
  Aspect-ratio: 1:1
  Background: #F8F8F8 (light gray)
  Position: relative

Badge (optional, top-left):
  Position: absolute
  Top: 8px
  Left: 8px
  Padding: 4px 8px
  Border-radius: 4px
  Font-size: 10px
  Font-weight: 600

  Badge types:
    "New": bg #5CBFB5, color #FFFFFF
    "Express Delivery": bg #4CAF50, color #FFFFFF
    "Best Seller": bg #E8A0B0, color #FFFFFF

Heart icon (top-right):
  Position: absolute
  Top: 8px
  Right: 8px
  Size: 24px
  Color: #CCCCCC (outline)

Share icon (bottom-right of image):
  Position: absolute
  Bottom: 8px
  Right: 8px
  Size: 20px
  Color: #999999

Info section:
  Padding: 12px

  Current price:
    Font-size: 16px
    Font-weight: 700
    Color: #1A1A1A

  Original price:
    Font-size: 14px
    Color: #999999
    Text-decoration: line-through
    Margin-left: 8px

  Discount:
    Font-size: 12px
    Color: #D42426
    Margin-top: 4px

  Product name:
    Font-size: 14px
    Color: #1A1A1A
    Margin-top: 4px
    Max-lines: 2
    Overflow: ellipsis
```

### 6. Filter Pill (Price Range)

```
Height: 36px
Padding: 0 16px
Border: 1px solid #E0E0E0
Border-radius: 18px (fully rounded)
Background: #FFFFFF
Font-size: 13px
Color: #333333

Selected state:
  Background: #D42426
  Border-color: #D42426
  Color: #FFFFFF

Container:
  Horizontal scroll
  Gap: 8px between pills
  Padding: 12px 16px
```

### 7. Search Input

```
Height: 48px
Border: 2px solid #C87941 (orange)
Border-radius: 8px
Background: #FFFFFF
Padding: 0 16px

Left icon:
  Magnifying glass
  Size: 20px
  Color: #999999
  Margin-right: 8px

Input text:
  Font-size: 14px
  Color: #1A1A1A

Placeholder:
  Font-size: 14px
  Color: #CCCCCC
```

### 8. Button Styles

#### Primary Button (Add to Cart, Sign In, Proceed to Checkout)
```
Height: 50px
Border-radius: 8px
Background: #D42426
Color: #FFFFFF
Font-size: 16px
Font-weight: 700
Text-transform: uppercase (ADD TO CART, PROCEED TO CHECKOUT)
Icon + text layout
Width: 100% (within container)
```

#### Secondary Button (Write a Review)
```
Height: 40px
Border-radius: 8px
Background: #D42426
Color: #FFFFFF
Font-size: 14px
Font-weight: 600
Width: auto (fits content)
Padding: 0 24px
```

#### Ghost Button (Need Help, Chat with us)
```
Height: 48px
Border-radius: 8px
Background: #FDF0EC (light peach)
Color: #D42426
Font-size: 14px
Font-weight: 600
Width: 48% (50/50 split)
Icon + text layout
```

#### Icon Button (Wishlist, Chat in bottom bar)
```
Size: 48px (square)
Border-radius: 8px
Background: #F0E6DC (warm peach)
Icon: 24px
Icon color: #D42426
```

### 9. Form Input

```
Height: 48px
Border: 1px solid #E0E0E0
Border-radius: 8px
Background: #FFFFFF
Padding: 0 16px

Label:
  Font-size: 12px
  Color: #666666
  Margin-bottom: 4px

Input text:
  Font-size: 14px
  Color: #1A1A1A

Placeholder:
  Font-size: 14px
  Color: #CCCCCC

Right icon (optional):
  Size: 20px
  Color: #999999
  Position: absolute, right 12px
```

### 10. Bottom Sheet (Gold Scheme)

```
Container:
  Position: fixed, bottom
  Width: 100%
  Height: ~40% of screen
  Background: #FDF0EC
  Border-radius: 16px 16px 0 0
  Box-shadow: 0 -4px 20px rgba(0,0,0,0.1)

Content:
  Padding: 24px
  Display: grid
  Grid-template: 1fr 1fr (2x2)
  Gap: 12px

Action card:
  Background: #FFFFFF
  Border: 1px solid #F0E6DC
  Border-radius: 12px
  Padding: 16px
  Display: flex
  Align-items: center
  Gap: 12px

  Icon:
    Size: 32px
    Color: #C87941 (orange)

  Text:
    Font-size: 14px
    Font-weight: 600
    Color: #1A1A1A
```

### 11. Product Detail — Sticky Bottom Bar

```
Position: fixed, bottom
Height: 64px
Background: #FFFFFF
Border-top: 1px solid #F0F0F0
Display: flex
Align-items: center
Padding: 0 12px
Gap: 8px

Wishlist button:
  Width: 48px
  Height: 48px
  Border-radius: 8px
  Background: linear-gradient(135deg, #F0E6DC, #E8D5C4)
  Icon: 24px, white heart

Chat button:
  Width: 48px
  Height: 48px
  Border-radius: 8px
  Background: #FFFFFF
  Border: 1px solid #D42426
  Icon: 24px, #D42426

Add to Cart button:
  Flex: 1
  Height: 48px
  Border-radius: 8px
  Background: #D42426
  Color: #FFFFFF
  Font-size: 16px
  Font-weight: 700
  Icon: lock/bag
  Text: ADD TO CART
```

### 12. Cart Progress Stepper

```
Container:
  Display: flex
  Align-items: center
  Padding: 16px
  Gap: 0

Step:
  Display: flex
  Align-items: center
  Gap: 8px

  Circle:
    Width: 24px
    Height: 24px
    Border-radius: 50%
    Border: 2px solid #E0E0E0 (inactive)
    Background: #FFFFFF

    Active:
      Border-color: #4CAF50
      Background: #4CAF50

  Label:
    Font-size: 14px
    Color: #666666 (inactive)
    Color: #1A1A1A (active)

Connector:
  Flex: 1
  Height: 2px
  Background: #E0E0E0 (inactive)
  Background: #4CAF50 (active)
  Margin: 0 8px
```

### 13. Price Breakup Table

```
Container:
  Background: #FDF0EC
  Border-radius: 8px
  Padding: 16px

Row:
  Display: flex
  Justify-content: space-between
  Padding: 8px 0
  Border-bottom: 1px solid #F0E6DC

Column widths:
  Component: 30%
  Rate: 20%
  Weight: 20%
  Discount: 15%
  Value: 15%

Text:
  Component name: 14px, #D42426 (red)
  Values: 14px, #1A1A1A
  Alignment: right (values), left (labels)
  Bold: Grand Total row
```

### 14. Trust Badges (Product Detail)

```
Container:
  Display: flex
  Justify-content: space-around
  Padding: 16px 0
  Border-top: 1px solid #F0F0F0
  Border-bottom: 1px solid #F0F0F0

Badge:
  Display: flex
  Flex-direction: column
  Align-items: center
  Gap: 8px

  Icon:
    Size: 32px
    Color: #C87941

  Label:
    Font-size: 11px
    Color: #666666
    Text-align: center
```

### 15. Discover More Card (Product Detail, Cart)

```
Container:
  Display: grid
  Grid-template: 1fr 1fr
  Gap: 12px
  Padding: 16px

Card:
  Background: #FDF0EC
  Border-radius: 12px
  Padding: 16px
  Display: flex
  Gap: 12px

  Icon:
    Size: 40px
    Color: #C87941

  Text:
    Font-size: 12px
    Color: #C87941
    Line-height: 1.4
```

---

## Spacing System

| Token | Value | Usage |
|-------|-------|-------|
| `xs` | 4px | Gap between icon/label |
| `sm` | 8px | Gap between related items |
| `md` | 12px | Gap between cards, list items |
| `lg` | 16px | Section padding, card padding |
| `xl` | 24px | Page padding, bottom sheet padding |
| `xxl` | 32px | Major section spacing |

---

## Border Radius

| Token | Value | Usage |
|-------|-------|-------|
| `none` | 0 | Banner (edge-to-edge) |
| `sm` | 4px | Badges |
| `md` | 8px | Buttons, inputs, cards |
| `lg` | 12px | Action cards, discover more cards |
| `xl` | 16px | Bottom sheet top corners |
| `full` | 50% | Category circles, avatar, stepper circles |

---

## Shadows

| Token | Value | Usage |
|-------|-------|-------|
| `card` | `0 2px 8px rgba(0,0,0,0.08)` | Product cards, floating elements |
| `sheet` | `0 -4px 20px rgba(0,0,0,0.1)` | Bottom sheet |
| `button` | `0 2px 4px rgba(0,0,0,0.1)` | Primary buttons (optional) |

---

## Animation Specs

| Element | Animation | Duration | Easing |
|---------|-----------|----------|--------|
| Banner auto-scroll | Slide left | 500ms | ease-in-out |
| Bottom sheet open | Slide up from bottom | 300ms | ease-out |
| Bottom sheet close | Slide down | 250ms | ease-in |
| Card tap feedback | Scale 0.98 | 100ms | ease-out |
| Page transition | Slide from right | 300ms | ease-in-out |
| Heart toggle | Scale bounce | 200ms | ease-out |
| Skeleton loader | Pulse opacity | 1500ms | linear (loop) |
