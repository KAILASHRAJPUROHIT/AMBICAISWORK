# 3D Product Pipeline — Aradhana Jewellers

> "See jewellery like it is in your hand before visiting the showroom."

This document defines the canonical product model for 3D-enabled products, GLB delivery rules, LOD budgets, and the 10 hero designs that ship first.

---

## 1. Canonical Product Model

The existing `Product` type in `src/services/products.ts` is extended with 3D fields. A product is 3D-enabled **only** when `glb` is populated. All 3D fields are optional so the current 2D catalogue continues to work unchanged.

```ts
export type Product3DConfig = {
  /** CDN or bundled GLB URL. Null means no 3D model available. */
  glbUrl: string | null;

  /** Poster/preview image shown while GLB downloads. Falls back to existing imageKey. */
  posterImageKey: string | null;

  /** Material variants available for this product. Empty = single default material. */
  materialVariants: MaterialVariant[];

  /** Metal purity options. Empty = use product.karat. */
  purityOptions: PurityOption[];

  /** Total weight in grams. Used for live-rate price estimation. */
  totalWeight: number | null;

  /** Stone details. Empty = no stones. */
  stones: StoneDetail[];

  /** Camera preset for the 3D viewer (position, target, fov). */
  cameraPreset: CameraPreset;

  /** Whether this product supports AR try-on. */
  arEligible: boolean;

  /** Current availability status. */
  availability: 'in_stock' | 'made_to_order' | 'enquiry_only';

  /** LOD URLs keyed by quality level. Populated by CDN delivery pipeline. */
  lod: {
    low: string;    // <1 MB, mobile fallback
    medium: string; // <3 MB, default on phone
    high: string;   // <5 MB, tablets / inspect mode
  };

  /** Bounding box dimensions in millimetres (real-world scale). */
  dimensions: { width: number; height: number; depth: number };
};

export type MaterialVariant = {
  id: string;               // e.g. "yellow_18k", "rose_22k", "white_18k"
  label: string;            // e.g. "18K Yellow Gold"
  metalColor: 'yellow' | 'rose' | 'white';
  purity: 18 | 22;
  glbUrl: string;           // variant-specific GLB (different material)
  hexAccent?: string;       // optional accent colour for UI
};

export type PurityOption = {
  karat: 18 | 22;
  label: string;            // e.g. "18K (750 Hallmark)"
  rateMultiplier: number;   // e.g. 0.75 for 18K (750/1000)
};

export type StoneDetail = {
  type: string;             // e.g. "diamond", "ruby", "emerald"
  count: number;
  totalCaratWeight: number;
  clarity: string | null;   // e.g. "VS1", null if not graded
  setting: string;          // e.g. "prong", "bezel", "channel"
};

export type CameraPreset = {
  position: [number, number, number];  // [x, y, z] in mm
  target: [number, number, number];    // look-at point in mm
  fov: number;                         // field of view in degrees
  near: number;                        // near clip plane mm
  far: number;                         // far clip plane mm
};

export type Product = {
  id: string;
  label: string;
  category: string;
  categoryName: string;
  karat: number | null;
  weight: number | null;
  imageKey: string;

  /** 3D configuration. Null = 2D-only product (existing behaviour). */
  threeD: Product3DConfig | null;
};
```

---

## 2. GLB Delivery Rules

### Material Requirements
- **PBR only** (metallic-roughness workflow). No Phong, Lambert, or unlit materials.
- Separate meshes for: gold body, stones, enamel, background.
- Each material variant gets its own GLB file (not a material swap at runtime).
- Gold colour must match real gold under neutral studio lighting.

### Scale and Geometry
- **Real-world scale in millimetres.** A 16mm ring width = 16 units in the GLB.
- Correct proportions verified against physical reference or CAD drawing.
- Clasp, hinge, and stone-setting detail modelled (not texture-mapped).
- No oversized source CAD files in the app. Only optimised GLB exports.

### Textures
- Embedded in the GLB (not external references).
- Default 1024px. 2048px only where visual inspection proves it necessary (e.g. intricate filigree).
- KTX2/Basis Universal compression preferred for mobile.

### LOD (Level of Detail)
| Level | Target Size | Triangle Budget | Use Case |
|-------|------------|-----------------|----------|
| `low` | <1 MB | <15K tris | Older phones, background cards |
| `medium` | <3 MB | <50K tris | Default on phones |
| `high` | <5 MB | <100K tris | Inspect mode, tablets |

- **Hard maximum: 10 MB** for any hero piece at highest LOD.
- No source files larger than 20 MB in the repository.

### CDN Delivery
- Production GLBs served from CDN (not bundled in APK).
- Bundled GLBs only for the first ring spike (Phase 1).
- Asset caching via Expo Asset API for offline use after first load.

### File Naming
```
{productId}_{variant}_{lod}.glb
example: RING-001_yellow_18k_high.glb
```

---

## 3. 10 Hero Designs

These are the first products to receive 3D models. They represent the breadth of Aradhana's catalogue and each has a distinct form factor.

| # | ID | Category | Design Name | Priority | Notes |
|---|-----|----------|-------------|----------|-------|
| 1 | RING-001 | Ring | Classic Band Ring | P0 | Simple gold band, 2 material variants (18K/22K) |
| 2 | RING-002 | Ring | Solitaire Setting | P0 | Prong-set stone, test stone rendering |
| 3 | RING-003 | Ring | Filigree Work | P0 | Intricate goldwork, tests geometry detail |
| 4 | EARR-001 | Earrings | Jhumka Classic | P0 | Bell shape, dangling element, test motion |
| 5 | EARR-002 | Earrings | Stud with Halo | P0 | Compact, stone-heavy, test diamond rendering |
| 6 | BGL-001 | Bangles | Plain Gold Bangle | P0 | Simple cylinder, tests circular geometry |
| 7 | BGL-002 | Bangles | Stone-Studded Bangle | P0 | Combines gold + stones |
| 8 | PEND-001 | Pendant | Mangalsutra Pendant | P0 | Chain attachment point, enamel detail |
| 9 | NECK-001 | Necklace | Short Necklace | P1 | Multi-element, larger scene, test performance |
| 10 | SET-001 | Bridal Set | Bridal Necklace + Earrings | P1 | Multi-piece composed scene |

**Selection rationale:**
- Rings, earrings, and bangles are Aradhana's highest-traffic categories.
- Each form factor tests a different rendering challenge (stone, filigree, motion, enamel).
- The bridal set tests the "Build Your Set" feature from Phase 3.

---

## 4. Assets/Data Required from Aradhana

### For Each Hero Design
1. **Physical reference photo** (front, side, back, clasp) — white background, no filters.
2. **CAD export** in STEP, IGES, or OBJ format — or photogrammetry scan.
3. **Material specification:**
   - Metal: 18K / 22K yellow / rose / white gold.
   - Stones: type, carat, count, clarity if available.
   - Enamel: colour, placement.
4. **Weight** in grams (exact or range).
5. **Dimensions** in mm (width, height, depth).
6. **Size range** (for rings: sizes available; for bangles: inner diameter).
7. **Availability:** in-stock, made-to-order, or enquiry-only.

### For Ongoing Catalogue
- Template CSV matching the canonical product model fields.
- Photo + CAD per new design added to 3D catalogue.
- Designate one contact at Aradhana for 3D asset review/approval.

---

## 5. Definition of Done — Phase 0

- [x] This document written and reviewed.
- [ ] Aradhana provides physical reference photos for all 10 hero designs.
- [ ] Aradhana provides CAD exports or agrees to photogrammetry workflow.
- [ ] Material specifications confirmed for all 10 hero designs.
- [ ] One ring (RING-001) GLB approved: correct gold colour, proportions, clasp detail.
- [ ] Canonical `Product3D` type integrated into `src/services/products.ts`.
- [ ] 10 hero designs added to `assets/products.json` with 3D fields populated.
- [ ] Poster images created for all 10 hero designs.
