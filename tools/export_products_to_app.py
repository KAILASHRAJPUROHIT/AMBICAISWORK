"""Export catalogue products into the Aradhana app (assets/products).

Reads data/catalogue_db.json, copies every entry that still has a real photo
on disk (output path, or output_aradhana/<category>/<label>.jpg fallback),
compresses it for mobile, writes assets/products.json plus a generated
TypeScript image-map module so Metro can statically resolve requires.

Usage:  python tools/export_products_to_app.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "catalogue_db.json"
APP = Path(r"C:\Users\kaila\Desktop\aradhana-app")
IMG_DIR = APP / "assets" / "products"
OUT_JSON = APP / "assets" / "products.json"
OUT_TS = APP / "src" / "services" / "productImages.ts"

CATEGORY_NAMES = {
    "earrings": "Earrings",
    "jhumka": "Jhumkas",
    "jhumka_22": "Jhumkas",
    "wati": "Wati",
    "ladies_rings": "Rings",
    "tops": "Tops",
    "bangles": "Bangles",
    # OLD OUTPUTS backup folders
    "bali18": "Balis",
    "bali22": "Balis",
    "bangle22": "Bangles",
    "earring22": "Earrings",
    "gentsring22": "Gents Rings",
    "gentsrings": "Gents Rings",
    "jhumka22": "Jhumkas",
    "ladiesring18": "Rings",
    "ladiesring22": "Rings",
}

IMAGE_INDEX: dict[str, Path] = {}
FOLDER_OF: dict[str, str] = {}

# Item-code prefix -> category (authoritative; folders are only a fallback).
# Derived from stock workbook label conventions (BG/BB bangles, ER earrings,
# GR gents rings, LR ladies rings, JR/JB jhumkas, BL bali, WT wati).
PREFIX_CATEGORY = {
    "BB": ("bangle22", "Bangles"),
    "BG": ("bangle22", "Bangles"),
    "BA": ("bangle22", "Bangles"),
    "ER": ("earring22", "Earrings"),
    "JR": ("jhumka22", "Jhumkas"),
    "JB": ("jhumka22", "Jhumkas"),
    "GR": ("gentsring22", "Gents Rings"),
    "LR": ("ladiesring22", "Rings"),
    "BL": ("bali22", "Balis"),
    "WT": ("wati22", "Wati"),
}


def find_source(entry: dict) -> Path | None:
    candidates = [
        Path(entry["output"]),
        ROOT / "photo_edit_output" / entry["label"] / "delivery_2400.jpg",
        ROOT / "photo_edit_output" / entry["label"] / "edited.jpg",
    ]
    for c in candidates:
        if c.is_file():
            return c
    return IMAGE_INDEX.get(entry["label"])


def build_image_index() -> dict[str, Path]:
    """Stem -> path for every product-sized jpg under known folders."""
    index: dict[str, Path] = {}
    search_roots = [
        ROOT / "output_aradhana",
        ROOT / "output",
        ROOT / "processed",
        ROOT / "data" / "_reset_archive_2026-08-21",
        ROOT / "backups" / "OLD OUTPUTS",
    ]
    for root_dir in search_roots:
        if not root_dir.is_dir():
            continue
        for p in root_dir.rglob("*.jpg"):
            name = p.name.lower()
            if any(tag in name for tag in ("before_after", "debug", "report", "_mask")):
                continue
            if p.stem not in index:
                index[p.stem] = p
                rel = p.relative_to(root_dir)
                FOLDER_OF[p.stem] = (
                    root_dir.name if len(rel.parts) == 1 else rel.parts[0].lower()
                )
    return index


def load_stock() -> dict[str, dict]:
    """label_no -> {carat, net_weight, gross_weight, variety} from latest workbook."""
    try:
        import sys

        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        import stock_excel  # noqa: PLC0415

        source = stock_excel.latest_stock_workbook(stock_excel.STOCK_DIR)
        snapshot = stock_excel.load_stock_workbook(source)
    except Exception as exc:  # noqa: BLE001
        print(f"stock workbook unavailable ({exc}); weights omitted")
        return {}
    out: dict[str, dict] = {}
    for row in snapshot.records:  # type: ignore[attr-defined]
        label = str(getattr(row, "label_no", "") or "").strip()
        if not label:
            continue
        # normalise 'BB22/1' / 'BB22_1' / 'BB22 1' -> 'BB221'
        norm = "".join(ch for ch in label.upper() if ch.isalnum())
        out[norm] = {
            "carat": getattr(row, "carat", None),
            "netWeight": getattr(row, "net_weight", None),
            "grossWeight": getattr(row, "gross_weight", None),
            "variety": getattr(row, "variety_name", None),
        }
    print(f"stock rows loaded : {len(out)} from {Path(str(source)).name}")
    return out


def main() -> None:
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    global IMAGE_INDEX
    IMAGE_INDEX = build_image_index()
    STOCK = load_stock()

    products: list[dict] = []
    for stem, src in sorted(IMAGE_INDEX.items()):
        fname = stem + ".jpg"
        dest = IMG_DIR / fname
        if not dest.is_file():
            im = Image.open(src).convert("RGB")
            im.thumbnail((900, 900))
            im.save(dest, quality=82)

        folder = FOLDER_OF.get(stem, "")
        prefix = stem[:2].upper()
        if prefix in PREFIX_CATEGORY:
            cat_key, category_name = PREFIX_CATEGORY[prefix]
        else:
            cat_key = folder.lower()
            category_name = CATEGORY_NAMES.get(cat_key)
            if category_name is None:
                base = cat_key.replace("18", "").replace("22", "")
                category_name = CATEGORY_NAMES.get(base, "Jewellery")
        karat = 18 if cat_key.endswith("18") else 22 if cat_key.endswith("22") else None

        net_weight = None
        norm_stem = "".join(ch for ch in stem.upper() if ch.isalnum())
        s = STOCK.get(norm_stem)
        if s:
            try:
                nw = s.get("netWeight")
                net_weight = float(nw) if nw is not None else None
            except (TypeError, ValueError):
                net_weight = None
            carat = s.get("carat")
            if carat and not karat:
                try:
                    karat = int(float(str(carat).replace("K", "")))
                except ValueError:
                    pass

        key = "".join(ch for ch in stem if ch.isalnum())
        products.append(
            {
                "id": stem,
                "label": stem,
                "category": cat_key or "uncategorised",
                "categoryName": category_name,
                "karat": karat,
                "weight": net_weight,
                "imageKey": key,
                "image": f"assets/products/{fname}",
            }
        )

    OUT_JSON.write_text(json.dumps(products, indent=1), encoding="utf-8")

    lines = ["// AUTO-GENERATED by tools/export_products_to_app.py - do not edit",
             "export const productImages: Record<string, number> = {"]
    for p in products:
        lines.append(f"  {p['imageKey']}: require('../../assets/products/{p['id']}.jpg'),")
    lines.append("};")
    OUT_TS.write_text("\n".join(lines) + "\n", encoding="utf-8")

    total_mb = sum(f.stat().st_size for f in IMG_DIR.glob("*.jpg")) / 1e6
    with_weight = sum(1 for p in products if p["weight"])
    print(f"products exported : {len(products)}")
    print(f"with stock weight : {with_weight}")
    print(f"asset size        : {total_mb:.1f} MB")


if __name__ == "__main__":
    main()
