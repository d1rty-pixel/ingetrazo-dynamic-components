# System 32 cabinet

A cabinet carcass with plinth, shelves and System 32 hole rows. Open
`system32-cabinet.igz`, or copy the cabinet into another document: it carries its
definition. Needs the Dynamic Components extension.

## Files

| File | What it is |
|---|---|
| `system32-cabinet.igz` | The model: the cabinet in its starting size (0.6 × 0.56 × 2.0 m) with English labels. This is what you share. |
| `build.py` | Builds the model again. Only needed when the formulas change. |
| `labels.json` | The labels of the attributes and parts in German, Spanish and French; `build.py` writes them into the document. |

## What it does

- **Carcass**: width, depth, height, board thickness (16 / 19 / 25 mm), back panel.
- **Plinth**: height and set-back; the sides run to the floor, a plinth panel closes the gap.
- **Shelves**: automatic (the number follows the height so every gap stays between
  the smallest and largest gap) or fixed. Shelves always sit on the hole raster. A
  warning appears when the limits cannot both be kept.
- **Back panel**: sits in a groove in the sides, the bottom and the top (10 mm from
  the rear edge, 8 mm deep, both options). Shelves, dividers and the back hole
  row stop in front of the groove. The grooves are cutters of the generator
  `board@1`; without a back panel they are off.
- **Dividers**: for every started 1000 mm of width the cabinet gets one divider
  between bottom and top, spread evenly (up to 1000 mm: none, 1001–2000 mm: one,
  and so on). The 1000 mm is the option *Divider for every started width of*.
  Every compartment gets the same shelves at the same heights. Dividers are drilled
  *through* in the same System 32 rows (a blind hole of the sides' depth from each
  face would meet in the middle of a 19 mm board). Bottom, top, back panel and
  plinth stay in one piece. To change one compartment on its own, Bake the cabinet
  first. This freezes it as plain boards (cutters and unused, hidden parts are
  removed).
- **Holes (System 32)**: four rows (left/right × front/back), Ø5 × 12 mm blind
  holes, 32 mm apart. The row is centred between the bottom and the top panel, so
  the first and the last hole are the same distance from them (the sides can be
  swapped left/right); that distance is never smaller than *Smallest distance
  first/last hole to bottom/top* (32 mm) and at most one step (32 mm) larger. The
  front row is 37 mm from the front edge; the back row is a multiple of
  32 mm behind it, as far back as the depth allows. Diameter and depth are options.

Resizing the cabinet recounts the holes and shelves and rebuilds the sides, so
holes stay round and 32 mm apart.

## How it is made

Nothing here is special to the extension; each row of holes is made of
what the interface offers:

- the sides use the geometry *Board with holes and pockets* (`board@1`);
- each hole row is one small cylinder part with *Cuts into* set to its side;
- its position, `Copies` (the number of holes) and `Hidden` are formulas, e.g.
  Z = `Parent!L0 + (Copy + 1)*Parent!Raster - Parent!Hole_D/2`;
- the options (row distance, diameter, depth) are ordinary attributes with a
  section.

`build.py` creates the same thing in code, for the model file.

## Building the model again

```
PYTHONPATH=<ingetrazo-source>:<this repo> python models/system32-cabinet/build.py [out.igz] [--lang de]
```

Without `out.igz` it overwrites `system32-cabinet.igz`. `--lang` is `en`, `de`,
`es` or `fr`; the file in this folder uses `en`. The tests use
`build.py` as their reference component (`tests/test_cabinet.py`).
