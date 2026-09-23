# Jewellery terminology & correct catalogue placement

Reference for the legacy processing categories and the 47 stock categories,
how each is worn, and how it must be staged/placed in a product photo. Read
this before writing any new jewel-generation or compositing prompt — the
placement mistakes found in the first showcase batch (rings shaped like flat
brooches, earrings floating instead of hanging from hooks) came from
treating every category the same instead of respecting what each piece
actually is. Verified against real jewellery photography/terminology
sources, not assumption.

## Earrings family — worn on the earlobe

| Category | What it is | Defining feature | Display |
|---|---|---|---|
| `earrings` | General/dangling drop style (jhumka-type default: dome top + hanging beads) | Dangles below the ear | Hangs FROM a stand's hook pins by its own post, dangling straight down by gravity |
| `tops` | Stud earrings | Sits FLUSH on the earlobe — nothing hangs below | Same hook-pin hang as above, but the piece itself is compact/flush-shaped |
| `ladies_bali` | Hoop earring, traditional | Circular hoop, smallest/simplest, closest to the ear, everyday wear | Hangs from hook pins, hoop shape visible |
| `mens_bali` | Hoop earring, masculine | Same hoop form, bolder/thicker, worn singly or as a pair | Hangs from hook pins |
| `jhumka` | Bell/dome-shaped drop earring | Dome and lower beads hang below the lobe | Hang from a real pin; top attached and dome freely below |
| `dull` / Dul | Traditional ear ornament (the stock spelling is `DULL`) | An ornament type here, not an instruction to make the gold dull | Attach to real earring pins/holes and preserve all lower components |
| `kaan_chain` | Ear-support chain | Joins the earring/lobe to a pin in the hair | Show both attachment ends and a natural curve; never float from one end |
| `nath`, `moti_nath` | Nose ring; `moti` denotes pearl-set styling | Hoop at the nostril, sometimes with a hair/ear chain | Face-on on a small pin/pad; keep any source chain untangled |

Bali ≠ tops ≠ earrings: a bali is a **hoop** (circular), tops are **studs**
(flush, no dangle), "earrings" defaults to a **dangling drop** style
(jhumka). Don't generate a bali as a stud or vice versa.

## Ring family — worn on a finger

| Category | What it is | Defining feature |
|---|---|---|
| `ladies_rings`, `gents_rings`, `silver`, `diamond` | Finger ring | **CLOSED CIRCULAR BAND** — the band's opening (the hole a finger goes through) must be visible in the photo. This is the single most important shape constraint: a ring that reads as a flat bar/brooch/cuff is wrong regardless of how good the metalwork looks. |

Display: stands **upright** in the ring box's velvet cushion slot, band
opening facing the camera — never lying flat/sideways across the cushion.

## Wrist family

| Category | What it is | Rigid or flexible | Worn | Display |
|---|---|---|---|---|
| `ladies_bracelet`, `gents_bracelet` | Bracelet | **Flexible** — chain-linked or hinged, has a clasp | Single piece, moves with the wrist | Rests/drapes over a wrist-form cushion, following its curve |
| `bangles` | Bangle | **Rigid**, thin, no clasp, slides over the hand | Worn **in stacks/sets** — a single bangle photo undersells it; show 2+ | Wraps fully around a cylindrical roller stand |
| `ladies_kada`, `gents_kada` | Kada | **Rigid**, thick, heavy, no clasp, slides over the hand | Worn **singly or in pairs** as a statement piece (traditionally unisex, cultural/spiritual significance — Punjabi kara, Rajasthani kada) | Wraps around a cylindrical roller stand, same as bangles but reads as one substantial piece, not a stack |
| `baby_braclet` | Small flexible child's bracelet | Flexible/clasped | Child wrist | Child-size cushion or natural oval on a pad |
| `baby_kadli` | Small rigid baby/child kada or bangle | Rigid | Child wrist | Child-scale cylinder or stable circle on a pad |
| `mangota` | Nazariya-style protective black-bead children's bracelet | Flexible, often black beads/charms | Child wrist | Small cushion/natural oval; preserve exact bead pattern |
| `baju_bandh` | Bajuband/armlet | Wraps around the **upper arm**, not the wrist | Upper arm between shoulder and elbow | Wide cylindrical arm-form or closed oval on a pad |

Kada vs bangle: both rigid and clasp-less, but a kada is thick/heavy/singular
(a "statement" piece); a bangle is thinner and conventionally shown as a set.
A bracelet is flexible (clasp/hinge) — never wrap it around a roller stand
like a bangle; it drapes over a cushion instead.

## Neck family

| Category | What it is | Defining feature | Display |
|---|---|---|---|
| `necklace` | General neck ornament | Broader, more elaborate than a plain chain, often with a design across the front | Drapes around the bust's neck curve, symmetric |
| `ladies_chains`, `gents_chains` | Chain | Plain/simple linked chain, thinner than a full necklace, often meant to carry a pendant | Same bust-drape |
| `mangalsutra_short`, `mangalsutra_long` | Mangalsutra | **Black beads on a gold chain + a gold/diamond pendant** — signifies marriage. North Indian style: shorter chain, pendant worn visibly. South Indian/thali style: longer chain, worn close to the heart, less visible. The black beads are the non-negotiable defining feature — a mangalsutra without them is just a necklace. | Drapes around bust, `_short` sits higher/more visible, `_long` hangs lower |
| `locket` | Pendant that **OPENS** | Has a hinge seam and a clasp catch — a compartment for a photo/keepsake. The hinge must be visible in the photo, or it just reads as a pendant. | Hangs from a bust's hook by its bail, straight down by gravity |
| `pendant` | Decorative hanging piece, **does NOT open** | Solid, no hinge — purely aesthetic | Same hook-hang as locket, but solid construction |
| `wati` | One or two cup-shaped gold centre pieces of a Maharashtrian mangalsutra | Neck jewellery for married women; not a bowl and not toe jewellery | Face-forward on a pendant pad/easel or centred in a short black-bead mangalsutra on a bust |
| `fancy_mala`, `haar_chain` | Long necklace/garland-style chain | Longer drop than a close necklace | Tall bust, symmetrical sides, lowest point centred |
| `necklace_set` | Matching necklace and earrings | Multiple coordinated components | Necklace on bust; earrings on side pins, all source pieces visible |
| `pendent_set` | Matching pendant and earrings | Multiple coordinated components | Pendant centred; matching earrings evenly at each side |
| `tikka` | Maang tikka/forehead ornament | Chain follows the centre hair parting; pendant rests on forehead | Vertical on pad/easel, hook at top and pendant below |

Locket ≠ pendant: the ONLY real difference is the opening compartment. If
the generated piece doesn't show a hinge/seam, it's a pendant, not a locket.

## Other stock forms

| Category | What it is | Display |
|---|---|---|
| `baby_ring` | Small child's finger ring | Ring slot/pad at child scale; closed band opening visible |
| `gold_coin` | Investment/gifting coin, not worn jewellery | Flat or slightly angled on a plinth/coin easel; complete edge and relief visible |

## Material catch-alls (not shapes)

`silver` and `diamond` are materials, not shapes — a "silver" or "diamond"
item could physically be any category above. The placement engine must infer
the visible physical form from the source or use the stock variety; it must
never assume that a material category is automatically a ring or necklace.

The executable source of truth is `ornament_placement.py`. It normalises
stock spellings and purity suffixes, then supplies both studio-support and
anatomical wearing instructions to every generation engine.
