"""Controlled Klein A/B: category-only baseline vs verified visual anchors.

No scanner prose or raw JSON is sent to Klein. Each B prompt contains at most
three identity-critical facts that were confirmed against the source. Both
arms use the same source, label/seed, white mode, one attempt and Klein setup.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

import comfy_local_img
import jewellery_image_policy


BASE = Path(__file__).resolve().parent
REPORT = BASE / "reports" / "verified_anchor_ab_2026-08-10"

CASES = [
    {
        "id": "LR18_13",
        "category": "ring",
        "source": BASE / "reports" / "adaptive_klein_2026-08-09" / "ring_roi" / "LR18_13_complete_roi.png",
        "quantity": 1,
        "item": "bypass ring",
        "anchors": [
            "one upper and one lower fish-scale open mesh panel",
            "a central diagonal ladder band with two rails and repeated vertical struts",
            "two asymmetric smooth solid terminal caps at opposite open ends",
        ],
    },
    {
        "id": "TP18_8",
        "category": "tops",
        "source": BASE / "capture_intake" / "55 TOPS 18" / "TP18_8.jpg",
        "quantity": 2,
        "item": "matching circular stud earrings",
        "anchors": [
            "one round clear centre stone in each stud",
            "one narrow red circular enamel band around each centre",
            "a textured yellow-gold outer rim with the same concentric proportions",
        ],
    },
    {
        "id": "JB22_27",
        "category": "jhumka",
        "source": BASE / "capture_intake" / "32 JHUMKA 22" / "JB22_27.jpg",
        "quantity": 2,
        "item": "matching jhumka earrings",
        "anchors": [
            "a round beaded floral top stud and small red connector accents",
            "one embossed yellow-gold bell dome below each stud",
            "a dense fringe of fine chains ending in small gold balls",
        ],
    },
    {
        "id": "BL18_4",
        "category": "bali",
        "source": BASE / "capture_intake" / "5 BALI 18" / "BL18_4.jpg",
        "quantity": 2,
        "item": "matching short curved bali earrings",
        "anchors": [
            "a short curved rectangular half-hoop silhouette",
            "exactly two parallel rows of small white stones on each front face",
            "exactly three parallel yellow-gold rails bordering and separating those two rows",
        ],
    },
    {
        "id": "LC18_7",
        "category": "locket",
        "source": BASE / "capture_intake" / "39 LOCKET 18" / "LC18_7.jpg",
        "quantity": 1,
        "item": "rectangular drop locket",
        "anchors": [
            "an open white-stone rectangular frame with elongated centre accents at top and bottom",
            "stacked yellow-gold C and S scrolls inside the frame",
            "one large round cream-white pearl drop attached below",
        ],
    },
]


def anchored_prompt(case: dict) -> str:
    quantity = int(case["quantity"])
    item = case["item"]
    anchors = "; ".join(case["anchors"][:3])
    prompt = (
        f"Create a floating catalogue photograph on pure white with exactly {quantity} {item} "
        f"from the reference. Preserve its photographed silhouette, orientation and proportions. "
        f"Keep {anchors}. Match photographed parts, component counts, materials and colours. "
        f"Keep the complete jewellery sharply detailed with even white space around it."
    )
    words = len(prompt.split())
    if not 45 <= words <= 80:
        raise ValueError(f"Prompt length {words} outside 45-80 words for {case['id']}")
    return prompt


def baseline_prompt(case: dict) -> str:
    return jewellery_image_policy.build_klein_white_product_prompt(case["category"], None)


def run_case(case: dict) -> dict:
    source = Path(case["source"])
    if not source.exists():
        raise FileNotFoundError(source)
    record = {
        "item_type": case["item"],
        "quantity": case["quantity"],
        "pair": case["quantity"] == 2,
    }
    common = {
        "jewel_path": str(source),
        "tag_path": "",
        "bg_path": "",
        "category": case["category"],
        "label": f"verified_anchor_ab_{case['id']}",
        "design_record_override": record,
    }
    outputs = {}
    for arm, prompt in (("baseline", baseline_prompt(case)), ("anchored", anchored_prompt(case))):
        result = comfy_local_img.generate(
            **common,
            isolation_prompt_override=prompt,
        )
        if result.get("error") and not result.get("output"):
            raise RuntimeError(f"{case['id']} {arm}: {result['error']}")
        source_output = Path(result["output"])
        destination = REPORT / f"{case['id']}_{arm}{source_output.suffix.lower()}"
        shutil.copy2(source_output, destination)
        outputs[arm] = {
            "output": str(destination),
            "prompt": prompt,
            "result": result,
        }
    return {"id": case["id"], "category": case["category"], "arms": outputs}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--case", action="append", help="limit to source id; repeatable")
    args = parser.parse_args()
    selected = [case for case in CASES if not args.case or case["id"] in args.case]
    if args.dry_run:
        for case in selected:
            prompt = anchored_prompt(case)
            print(f"{case['id']} ({len(prompt.split())} words): {prompt}")
        return 0

    REPORT.mkdir(parents=True, exist_ok=True)
    os.environ["KLEIN_WHITE_BACKGROUND_MODE"] = "1"
    os.environ["KLEIN_WHITE_MAX_ATTEMPTS"] = "1"
    results = [run_case(case) for case in selected]
    manifest = REPORT / "manifest.json"
    manifest.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
