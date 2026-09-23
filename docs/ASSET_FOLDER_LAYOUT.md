# V1 asset folder contract

The resolver uses the stock workbook's ornament type and variety. Variety
names are trimmed and normalised to uppercase for folder lookup. A blank
variety is `GENERAL`.

## Backgrounds

Preferred exact-variety layout:

```text
backgrounds/<THEME>/<ORNAMENT>/<VARIETY>/bg_<ornament>.jpg
```

Fallback order:

```text
backgrounds/<THEME>/<ORNAMENT>/bg_<ornament>_<VARIETY>.jpg
backgrounds/<THEME>/bg_<ornament>_<VARIETY>.jpg
backgrounds/<THEME>/<ORNAMENT>/GENERAL/bg_<ornament>.jpg
backgrounds/<THEME>/<ORNAMENT>/bg_<ornament>.jpg
backgrounds/<THEME>/bg_<ornament>.jpg
```

The last path is the existing legacy layout and remains supported.

## Models

Preferred exact-variety layout:

```text
models/<THEME>/<GROUP>/<ORNAMENT>/<POSE>/<VARIETY>/*.jpg
```

When no model theme is configured:

```text
models/<GROUP>/<ORNAMENT>/<POSE>/<VARIETY>/*.jpg
```

Fallback order is the matching `GENERAL` folder, then the matching pose
folder, then an existing legacy model whose filename positively identifies
the requested body-zone pose. A generic or unrelated pose is never selected
silently.

## Rule precedence

```text
explicit Manual Mode override
ornament + exact variety rule
ornament + GENERAL rule
ornament-wide rule
built-in ornament default
```

Missing configured assets are an explicit routing failure and send the source
item to the rejected lifecycle; the resolver does not substitute an unrelated
ornament, variety, or pose.
