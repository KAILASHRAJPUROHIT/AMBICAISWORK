"""Indian-jewellery semantics shared by studio and on-model generation.

The catalogue contains business labels, purity suffixes and legacy aliases
that are not interchangeable visual categories.  This module converts those
labels to a small set of physical placement profiles.  Prompts consume only
the operational guidance; cultural descriptions stay here so they cannot
accidentally become visual instructions.

The profiles were cross-checked against Indian brand glossaries/catalogues
(Tanishq, CaratLane, Kalyan, Malabar and PNG), NID/D'Source material and the
National Museum / Google Arts & Culture.  The local ``backgrounds`` library
was then audited theme by theme so the rules describe the props that actually
exist in this project.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OrnamentProfile:
    key: str
    name: str
    meaning: str
    wearer: str
    zone: str | None
    studio: str
    model: str
    set_rule: str = ""
    template_key: str | None = None
    model_codes: tuple[str, ...] = ()
    background_asset_key: str | None = None


def _p(
    key: str,
    name: str,
    meaning: str,
    wearer: str,
    zone: str | None,
    studio: str,
    model: str,
    *,
    set_rule: str = "",
    template_key: str | None = None,
    model_codes: tuple[str, ...] = (),
    background_asset_key: str | None = None,
) -> OrnamentProfile:
    return OrnamentProfile(
        key, name, meaning, wearer, zone, studio, model, set_rule,
        template_key, model_codes, background_asset_key,
    )


PROFILES: dict[str, OrnamentProfile] = {
    "generic": _p(
        "generic", "Jewellery", "unclassified jewellery", "unspecified", None,
        "Identify the ornament's physical form from Image 1, then use only a support that can physically hold that form.",
        "Identify how the exact physical form is worn and attach it only to that anatomical location; do not guess from material or decorative style.",
    ),
    "earrings": _p(
        "earrings", "Earrings", "ear ornaments, usually sold as a pair", "women/girls", "face",
        "Use the destination earring pins, holes or hooks. Attach each post or hook at a real contact point and let drops hang vertically by gravity; never float the pair or erase the stand.",
        "Attach at the earlobe piercing. Show both earrings in a front view or one complete near earring in profile, with hair clear of the design.",
        set_rule="If Image 1 is a pair, preserve exactly two equal pieces and their left/right orientation.",
        template_key="earrings",
    ),
    "jhumka": _p(
        "jhumka", "Jhumka", "bell- or dome-shaped Indian drop earrings", "women/girls", "face",
        "Hang each jhumka from a real earring pin or hook; keep the top attached and the bell-shaped lower part hanging freely below it without touching the base.",
        "Attach at the earlobe piercing and keep the dome/drop below the lobe at natural scale; do not turn it into a stud or hoop.",
        set_rule="Preserve the complete pair, matching domes, beads and dangles.", template_key="earrings",
    ),
    "tops": _p(
        "tops", "Tops", "compact stud earrings worn flush on the earlobe", "women/girls", "face",
        "Fix each stud face-forward to the stand's existing pin or hole. The decorative face sits at the attachment point; do not add a hanging drop unless Image 1 contains one.",
        "Place the compact stud flush on the earlobe piercing with the front motif facing camera; it must not dangle below the ear like a jhumka.",
        set_rule="Preserve exactly two matching studs when the source is a pair.", template_key="tops",
    ),
    "ladies_bali": _p(
        "ladies_bali", "Ladies Bali", "women's hoop earrings", "women/girls", "face",
        "Hang the hoop through the destination hook or pin so its circular opening remains visible and the hoop hangs naturally.",
        "Pass the hoop through the earlobe piercing; preserve the circular opening and realistic diameter relative to the ear.",
        set_rule="Keep a sold pair equal-sized and symmetrical.", template_key="ladies_bali",
    ),
    "mens_bali": _p(
        "mens_bali", "Men's Bali", "men's hoop earring", "men/boys", "face",
        "Hang the hoop through a real hook or pin and keep its opening visible. If Image 1 contains one piece, display one—never invent a second.",
        "Pass the exact hoop through the male earlobe piercing at conservative natural scale; respect whether the source is one piece or a pair.",
        template_key="mens_bali",
    ),
    "bali": _p(
        "bali", "Bali", "hoop earring; the stock category is not gender-specific", "adult/child, source-dependent", "face",
        "Hang each hoop through a real stand pin or hook with its circular opening visible. Preserve whether Image 1 contains one hoop or a pair.",
        "Attach through the earlobe piercing. Use the selected model's gender/age rather than assuming ladies or gents, and retain the source hoop's natural diameter.",
        template_key="ladies_bali",
    ),
    "dul": _p(
        "dul", "Dul", "traditional ear ornament/earring (catalogue spelling: DULL)", "women/girls", "face",
        "Treat this as an ear ornament, not as a colour finish. Attach each piece to real earring pins or holes and let any lower elements hang naturally.",
        "Attach at the earlobe/ear according to Image 1's construction; keep the full ear ornament visible and hair clear.",
        set_rule="Preserve the source component count and pair symmetry.", template_key="earrings",
    ),
    "kaan_chain": _p(
        "kaan_chain", "Kaan Chain", "ear-support chain connecting an earring to the hair", "women/girls", "face",
        "Show the complete chain as a gentle supported curve between two real attachment points. On a flat pad, arrange the pair symmetrically without knots; never hang it from only one unsupported point.",
        "Attach the lower end to the earring/lobe and the upper end to a hair pin above or behind the ear. The chain follows the side of the face without crossing the eye, mouth or neck.",
        set_rule="For a pair, preserve two mirrored ear-to-hair chains and every terminal fitting.", template_key="earrings",
    ),
    "nath": _p(
        "nath", "Nath", "Indian nose ring, often bridal", "women/girls", "face",
        "Present the nose ring face-on on a small pin, pad or flat plinth with its hoop/opening unobstructed. If it has a support chain, lay the chain in a clean natural curve.",
        "Attach the ring at the nostril piercing. If Image 1 has a chain, connect its other end to the hair or ear; if it has no chain, do not invent one.",
        template_key="nath",
    ),
    "moti_nath": _p(
        "moti_nath", "Moti Nath", "pearl-set nath or nose ring", "women/girls", "face",
        "Support the hoop on a small pin/pad or lay it face-on so every pearl and the circular opening remain visible; arrange any chain in a clean curve.",
        "Attach at the nostril and preserve the exact pearl count and spacing. Connect a source chain to hair/ear only when Image 1 actually contains it.",
        template_key="nath",
    ),
    "maang_tika": _p(
        "maang_tika", "Maang Tikka", "forehead ornament suspended from the centre hair parting", "women/girls", "bridal",
        "Lay it vertically on a flat pad/easel: hook or chain at the top, centre pendant below, all links untangled. Do not use an earring T-stand.",
        "Anchor the chain in the centre hair parting and place the pendant on the midline of the forehead above the brows; never offset it like an earring.",
        template_key="maang_tika",
    ),
    "necklace": _p(
        "necklace", "Necklace", "decorative neck ornament", "women", "neck",
        "Drape it symmetrically around the destination bust/neck form, following both shoulders; centre the principal motif and keep the clasp behind the bust.",
        "Drape around the neck and collarbones with the centre motif on the chest midline; follow the body contour and keep both sides connected behind the neck.",
        template_key="necklace",
    ),
    "necklace_set": _p(
        "necklace_set", "Necklace Set", "matching necklace and earrings sold together", "women", "neck",
        "Place the necklace symmetrically on the bust and attach the matching earrings to two side pins or place them evenly beside the bust. Every source component must remain visible.",
        "Wear the necklace at the neck and the matching earrings at both earlobes in the same image; do not omit or invent set pieces.",
        set_rule="Image 1 is a set: preserve its exact necklace-and-earring component count.", template_key="necklace",
    ),
    "fancy_mala": _p(
        "fancy_mala", "Fancy Mala", "decorative long necklace or garland-style neckpiece", "women", "neck",
        "Use a tall bust. Drape both sides evenly and let the centre element fall lower than a short necklace without pooling on the base.",
        "Wear as a long necklace over the upper chest, centred and following gravity; keep its intended length visibly longer than a close necklace.",
        template_key="necklace",
    ),
    "haar_chain": _p(
        "haar_chain", "Haar Chain", "long necklace/haar chain", "women", "neck",
        "Drape on a tall bust with equal side lengths and a centred lowest point; do not coil it on a small pedestal.",
        "Wear as a long chain or haar down the chest with the centre line aligned to the sternum and the clasp behind the neck.",
        template_key="necklace",
    ),
    "ladies_chains": _p(
        "ladies_chains", "Ladies Chain", "women's neck chain", "women", "neck",
        "Drape the full chain around a bust in one clean symmetrical loop; keep links untangled and clasp behind the bust.",
        "Drape naturally around a woman's neck/collarbone at the source length.", template_key="ladies_chains",
    ),
    "gents_chains": _p(
        "gents_chains", "Gents Chain", "men's neck chain", "men", "neck",
        "Drape the full chain around a masculine bust in one clean loop with the lowest point centred and clasp behind.",
        "Drape naturally around a man's neck and upper chest at the source length, following the open collar or kurta neckline.", template_key="gents_chains",
    ),
    "chain": _p(
        "chain", "Chain", "neck chain; stock category does not encode gender", "source/model-dependent", "neck",
        "Drape the complete chain in one clean symmetrical loop on a neutral bust; do not infer a pendant or change link style.",
        "Wear at the neck on the selected appropriate model. Preserve the source length and link scale; do not infer gender from metal colour alone.",
        template_key="ladies_chains",
    ),
    "mangalsutra_short": _p(
        "mangalsutra_short", "Short Mangalsutra", "short black-bead marriage necklace", "married women", "neck",
        "Drape close to the neckline on a short bust, keep black-bead sections and gold links exact, and centre the pendant.",
        "Wear close to the neckline on a married Indian woman; centre the pendant and preserve the exact black-bead pattern.", template_key="mangalsutra_short",
    ),
    "mangalsutra_long": _p(
        "mangalsutra_long", "Long Mangalsutra", "long black-bead marriage necklace", "married women", "neck",
        "Use a tall bust and let the complete chain fall symmetrically down the chest, with black-bead sections exact and pendant centred.",
        "Wear long over the chest on a married Indian woman; keep the pendant on the sternum midline and preserve black-bead spacing.", template_key="mangalsutra_long",
    ),
    "wati": _p(
        "wati", "Wati", "the one or two gold cup-shaped centre pendants of a Maharashtrian mangalsutra", "married women", "neck",
        "This is mangalsutra jewellery, NOT a ceremonial bowl and NOT a toe ring. Display the exact Wati cup component(s) face-forward on a pendant pad/easel or as the centre of a short black-bead mangalsutra draped on a bust. Never place it inside a bowl-shaped prop.",
        "Wear the exact Wati cup component(s) centred at the front of a black-bead mangalsutra on a married Indian woman's neck. Preserve whether the source has one cup or two and do not reshape them into flat discs.",
        template_key="mangalsutra_short", background_asset_key="mangalsutra_short",
    ),
    "pendant": _p(
        "pendant", "Pendant", "solid decorative piece suspended from a chain", "women/men/kids, source-dependent", "neck",
        "Place the pendant face-on against a small easel/pad or hang it by its own bail. If Image 1 includes a chain, drape that chain; otherwise do not invent a decorative chain.",
        "Suspend the exact pendant by its bail from a simple proportionate chain at the chest midline; retain the source pendant size and orientation.", template_key="pendant",
    ),
    "pendant_set": _p(
        "pendant_set", "Pendant Set", "matching pendant and earrings", "women", "neck",
        "Show the pendant face-on at centre and attach or arrange the matching earrings evenly on both sides. Preserve all source pieces and never merge them.",
        "Wear the pendant on a simple chain at the chest midline and the matching earrings at both earlobes; all set components must be visible.",
        set_rule="Preserve the exact pendant-and-earring component count.", template_key="pendant",
    ),
    "locket": _p(
        "locket", "Locket", "pendant with an opening compartment", "women/men/kids, source-dependent", "neck",
        "Hang the locket by its bail or rest it face-on on a small pad/easel. Preserve the hinge, seam and clasp that distinguish it from a solid pendant.",
        "Suspend at the chest midline from a simple chain, with the locket face and its hinge/seam visible; do not convert it into a flat pendant.", template_key="locket",
    ),
    "ring": _p(
        "ring", "Ring", "finger ring; wearer is determined by the stock item", "source/model-dependent", "hand",
        "Insert the band into the destination ring slot or centre it upright on the cushioned crease. Keep the band opening visible and crown upright; never lay it flat like a brooch.",
        "Fit the closed band around one appropriate finger below the knuckle at natural scale, with the crown centred on top.",
        template_key="ladies_rings",
    ),
    "ladies_rings": _p(
        "ladies_rings", "Ladies Ring", "women's finger ring", "women", "hand",
        "If the destination box has a raised ring groove/slot, insert the band there. If it is a plain cushioned box with a horizontal crease/line across the pad instead, centre the ring directly over that line, band opening visible and crown upright — never off to one side or lying flat like a brooch.",
        "Fit the closed band around one woman's finger below the knuckle, with the crown centred on top and neighbouring fingers unobstructed.", template_key="ladies_rings",
    ),
    "gents_rings": _p(
        "gents_rings", "Gents Ring", "men's finger ring", "men", "hand",
        "If the destination box has a raised ring groove/slot, insert the band there. If it is a plain cushioned box with a horizontal crease/line across the pad instead, centre the ring directly over that line, band opening visible and crown upright.",
        "Fit the closed band around one man's finger below the knuckle with natural masculine scale and the crown centred on top.", template_key="gents_rings",
    ),
    "baby_ring": _p(
        "baby_ring", "Baby Ring", "small ring made for a child", "children", "hand",
        "If the destination box has a raised ring groove/slot, insert the band there. If it is a plain cushioned box with a horizontal crease/line across the pad instead, centre the ring directly over that line. Do not enlarge it to adult scale.",
        "Fit it around one child's finger at child-safe natural scale; the band must not be enlarged to an adult statement ring.", template_key="ladies_rings", model_codes=("KG", "KB"),
    ),
    "bangles": _p(
        "bangles", "Bangles", "rigid circular wrist ornaments, often sold in pairs or stacks", "women/girls", "wrist",
        "Slide the complete rigid circles over the destination cylinder/T-bar and stack them in source order. On a flat plinth, rest them as stable overlapping circles with openings visible.",
        "Slide the rigid bangles over the hand onto the wrist; preserve the source count and stack order without embedding them in skin.",
        set_rule="Never duplicate a single source bangle merely to make a decorative stack.", template_key="bangles",
    ),
    "ladies_bracelet": _p(
        "ladies_bracelet", "Ladies Bracelet", "flexible or articulated wrist jewellery with a clasp", "women", "wrist",
        "Drape it over the curved cushion/C-riser following the curve, with clasp and ends connected. On a flat pad, arrange it in a natural oval.",
        "Wrap the flexible bracelet around a woman's wrist with clasp closed and links following the wrist contour.", template_key="ladies_bracelet",
    ),
    "gents_bracelet": _p(
        "gents_bracelet", "Gents Bracelet", "men's flexible or articulated wrist jewellery", "men", "wrist",
        "Drape it over the curved cushion/C-riser or cylinder with its clasp closed; on a flat plinth arrange a stable natural oval.",
        "Wrap around a man's wrist with clasp closed and links following the forearm contour at natural scale.", template_key="gents_bracelet",
    ),
    "baby_bracelet": _p(
        "baby_bracelet", "Baby Bracelet", "small flexible wrist bracelet for a child", "children", "wrist",
        "Drape on a small curved cushion in a natural oval, clasp visible and closed. Do not enlarge to adult wrist scale.",
        "Wrap around a child's wrist with gentle natural clearance, clasp closed and no adult-scale enlargement.", template_key="ladies_bracelet", model_codes=("KG", "KB"),
    ),
    "baby_kadli": _p(
        "baby_kadli", "Baby Kadli", "baby kada/bangle for the wrist", "babies/children", "wrist",
        "Place the small rigid circle around a child-scale cylinder or rest it stably on a small pad with its opening visible; preserve whether it is a pair.",
        "Fit around a child's wrist at child scale with safe natural clearance; do not place on an adult wrist or ankle.", template_key="ladies_kada", model_codes=("KG", "KB"),
    ),
    "ladies_kada": _p(
        "ladies_kada", "Ladies Kada", "rigid substantial women's wrist ornament", "women", "wrist",
        "Slide it around the destination cylinder/T-bar or rest it as a stable upright/angled circle on a plinth, opening visible.",
        "Fit the rigid kada around a woman's wrist with natural clearance; preserve its substantial thickness and exact opening mechanism.", template_key="ladies_kada",
    ),
    "gents_kada": _p(
        "gents_kada", "Gents Kada", "rigid substantial men's wrist ornament", "men", "wrist",
        "Slide it around the destination cylinder/T-bar or rest it as a stable upright/angled circle on a plinth, opening visible.",
        "Fit the rigid kada around a man's wrist with natural clearance; keep its weight, thickness and opening mechanism exact.", template_key="gents_kada",
    ),
    "bajuband": _p(
        "bajuband", "Bajuband", "armlet worn around the upper arm", "women traditionally; men historically", "upper_arm",
        "Wrap the complete armlet around a wide cylindrical arm-form or drape it in a closed oval on a flat pad. Keep ties/chains visible and never treat it as a wrist bangle.",
        "Fit around the upper arm between shoulder and elbow, following the arm contour. Do not place it at the wrist, neck or waist.", template_key=None, model_codes=("F2", "F3"),
    ),
    "mangota": _p(
        "mangota", "Mangota", "Nazariya-style children's bracelet, commonly with protective black beads", "babies/children", "wrist",
        "Arrange as a child-size bracelet on a small curved cushion or in a natural closed oval on a pad. Preserve every black bead, charm and clasp.",
        "Wrap around a child's wrist at child scale with the black-bead/charm pattern exact; never place at an adult neck or wrist.", template_key="ladies_bracelet", model_codes=("KG", "KB"),
    ),
    "gold_coin": _p(
        "gold_coin", "Gold Coin", "investment or gifting coin; not worn", "not worn", "hand",
        "Lay the coin flat or at a slight supported angle on a clean plinth/coin easel, complete circular edge visible. Preserve denomination, relief and both-sided identity; never turn it into jewellery.",
        "This item is not worn. Show the exact coin held carefully between clean fingertips or resting on an open palm at true coin scale; do not add a chain, bezel or ring mount.", template_key="ladies_rings",
    ),
    "material": _p(
        "material", "Material Category", "a material/finish label rather than a physical ornament form", "source-dependent", None,
        "Determine whether Image 1 is a ring, earring, neckpiece or wrist piece and apply that form's support rule. Never infer shape from the words silver or diamond.",
        "Use the physical ornament form visible in Image 1 and the selected compatible model pose; never default a material label to the neck or face.",
    ),
}


_ALIASES = {
    "earring": "earrings", "earrings": "earrings",
    "jhumka": "jhumka", "jhumki": "jhumka", "jhumkas": "jhumka",
    "tops": "tops", "top": "tops",
    "ladies_bali": "ladies_bali", "mens_bali": "mens_bali", "men_bali": "mens_bali", "bali": "bali",
    "dull": "dul", "dul": "dul",
    "kaan_chain": "kaan_chain", "ear_chain": "kaan_chain", "sahara": "kaan_chain",
    "nath": "nath", "moti_nath": "moti_nath",
    "tikka": "maang_tika", "maang_tika": "maang_tika", "mang_tikka": "maang_tika",
    "necklace": "necklace", "necklace_set": "necklace_set",
    "fancy_mala": "fancy_mala", "haar_chain": "haar_chain",
    "ladies_chain": "ladies_chains", "ladies_chains": "ladies_chains",
    "gents_chain": "gents_chains", "gents_chains": "gents_chains", "chain": "chain",
    "ms_long": "mangalsutra_long", "mangalsutra_long": "mangalsutra_long",
    "mss_short": "mangalsutra_short", "ms_short": "mangalsutra_short", "mangalsutra_short": "mangalsutra_short",
    "wati": "wati",
    "pendent": "pendant", "pendant": "pendant", "pendent_set": "pendant_set", "pendant_set": "pendant_set",
    "locket": "locket",
    "ring": "ring", "ladies_ring": "ladies_rings", "ladies_rings": "ladies_rings",
    "gents_ring": "gents_rings", "gents_rings": "gents_rings", "baby_ring": "baby_ring",
    "bangle": "bangles", "bangles": "bangles",
    "ladies_bracelet": "ladies_bracelet", "gents_bracelet": "gents_bracelet",
    "baby_braclet": "baby_bracelet", "baby_bracelet": "baby_bracelet",
    "baby_kadli": "baby_kadli", "baby_kada": "baby_kadli",
    "ladies_kada": "ladies_kada", "gents_kada": "gents_kada",
    "baju_bandh": "bajuband", "bajuband": "bajuband", "bazu_band": "bajuband",
    "mangota": "mangota",
    "gold_coin": "gold_coin", "coin": "gold_coin",
    "silver": "material", "diamond": "material",
}


def normalise_category(value: str | None) -> str:
    """Return a canonical profile key from a stock label or processing key."""

    text = re.sub(r"[^a-z0-9]+", "_", (value or "").strip().casefold()).strip("_")
    # Stock folders begin with a catalogue sequence number (for example
    # ``32 JHUMKA 22``). It is metadata, not part of the jewellery category.
    # Without removing it, live Klein prompts silently resolve to ``generic``
    # and lose category-specific piece-count and placement rules.
    text = re.sub(r"^\d+_", "", text)
    # Purity/weight suffixes are stock metadata, not a change of body zone.
    text = re.sub(r"_(?:18|20|22|24)(?:_?k|_?kt)?$", "", text)
    text = re.sub(r"_(?:0_?025|0_?050|0_?100|0_?200|0_?250|0_?300|0_?500|0_?750|1|2|5|10|20)_?(?:g|gm|m)?$", "", text)
    return _ALIASES.get(text, text if text in PROFILES else "generic")


def get_profile(category: str | None) -> OrnamentProfile:
    return PROFILES[normalise_category(category)]


def studio_guidance(category: str | None) -> str:
    profile = get_profile(category)
    lines = [f"- CATEGORY PLACEMENT ({profile.name}): {profile.studio}"]
    if profile.set_rule:
        lines.append(f"- COMPONENT RULE: {profile.set_rule}")
    return "\n".join(lines)


def model_guidance(category: str | None) -> str:
    profile = get_profile(category)
    lines = [f"- CATEGORY WEAR ({profile.name}): {profile.model}"]
    if profile.set_rule:
        lines.append(f"- COMPONENT RULE: {profile.set_rule}")
    return "\n".join(lines)


def background_asset_category(category: str | None) -> str:
    """Return the reviewed background asset key for a processing category.

    The existing Wati backgrounds depict a literal bowl.  Brand references
    and the project's stock varieties show that this catalogue's Wati is the
    mangalsutra centre component, so it must use a neckwear background until
    dedicated Wati assets are created.  No asset is deleted or overwritten.
    """

    normalized = normalise_category(category)
    profile = get_profile(category)
    if profile.background_asset_key:
        return profile.background_asset_key
    # Bug fixed 2026-08-02: this used to fall back to the RAW, un-normalized
    # `category` argument — for purity-suffixed stock categories like
    # "tops_22" that have no explicit background_asset_key override, that
    # returned "tops_22" unchanged even though normalise_category() had
    # already correctly reduced it to "tops" to find the profile above. The
    # background asset files on disk are only ever named by the base key
    # (bg_tops.jpg, never bg_tops_22.jpg), so every purity-suffixed category
    # 404'd on its background thumbnail and the studio-generation background
    # lookup alike. Use the normalized key here too, not the raw input.
    # Keep semantic identity separate from physical prop reuse.  These
    # profiles have precise prompts/model zones but the current background
    # library has only the compatible support named on the right.
    compatible_prop = {
        "ring": "ladies_rings",
        "baby_ring": "ladies_rings",
        "baby_bracelet": "ladies_bracelet",
        "baby_kadli": "ladies_kada",
        "bajuband": "bangles",
        "bali": "ladies_bali",
        "chain": "ladies_chains",
        "dul": "earrings",
        "jhumka": "earrings",
        "kaan_chain": "earrings",
        "nath": "earrings",
        "moti_nath": "earrings",
        "fancy_mala": "mangalsutra_long",
        "haar_chain": "mangalsutra_long",
        "mangota": "ladies_bracelet",
        "necklace_set": "necklace",
        "pendant_set": "pendant",
        "maang_tika": "pendant",
        "gold_coin": "silver",
        "material": "silver",
    }
    return compatible_prop.get(normalized, normalized)


def template_profile(category: str | None) -> tuple[str | None, str | None, tuple[str, ...]]:
    """Return ``(template_key, zone, explicit_model_codes)`` for model_engine."""

    profile = get_profile(category)
    return profile.template_key, profile.zone, profile.model_codes

