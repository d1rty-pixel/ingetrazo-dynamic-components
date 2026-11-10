# SketchUp formula functions

What SketchUp's own **Component Attributes** dialog offers, compared with what
`formula.py` implements. This is the *feature* list for compatibility (DESIGN.md
section 5); the safety rules (no `eval`, limits, fail closed) apply to every entry.

**Source:** screenshot of SketchUp's Component Attributes dialog, tab *Functions*
("Select a spreadsheet function..."), taken 2026-11-09:
[img/sketchup-functions-1.png](img/sketchup-functions-1.png).
The list scrolls and the screenshot shows only part of it: all of
*Math Functions* and the start of *SketchUp Functions* (up to `LAT()`). Further
entries and categories are not covered yet; add them from more screenshots.

Signatures are as SketchUp shows them. Semantics marked **(to verify)** are not
documented in the screenshot; check them against SketchUp before implementing.

Status: **yes** = in `formula._FUNCS` / `_LAZY`; **no** = missing.

## Math Functions

| SketchUp signature | Status | Notes |
|---|---|---|
| `ABS(number)` | yes | |
| `CEILING(number, significance)` | yes | SketchUp requires `significance`; ours defaults it to 1 (superset). Ours uses `ABS(significance)` and rejects 0; behaviour with a negative number and positive significance **(to verify)** |
| `DEGREES(number)` | yes | |
| `EVEN(number)` | no | Excel meaning: round away from zero to the next even integer **(to verify)** |
| `EXP(number)` | no | Must fail closed on overflow (result not finite) |
| `FLOOR(number, significance)` | yes | As `CEILING` |
| `INT(number)` | yes | Rounds down (toward −∞), like Excel |
| `ISEVEN(number)` | no | Returns bool |
| `ISODD(number)` | no | Returns bool |
| `LN(number)` | no | Error for `number <= 0` |
| `LOG10(number)` | no | Error for `number <= 0` |
| `ODD(number)` | no | Excel meaning: round away from zero to the next odd integer **(to verify)** |
| `POWER(base, power)` | no | Same as the `^` operator, which exists; reuse its overflow handling |
| `PI()` | yes | |
| `RADIANS(number)` | yes | |
| `RAND()` | no | Non-deterministic, see below |
| `RANDBETWEEN(bottom, top)` | no | Non-deterministic, see below |
| `ROUND(number, decimal_places)` | yes | SketchUp requires `decimal_places`; ours defaults it to 0. Half away from zero |
| `SIGN(number)` | no | −1, 0 or 1 |
| `SQRT(number)` | yes | |

## SketchUp Functions (start of the list only)

| SketchUp signature | Status | Notes |
|---|---|---|
| `CHOOSE(index, value1, value2, ...valueN)` | yes | Lazy: only the chosen value is evaluated; index out of range is an error |
| `CURRENT("attributeName")` | no | Current value of the named attribute **(exact meaning to verify)** |
| `EDGES()` | no | Geometry query: number of edges **(to verify)** |
| `FACEAREA("materialName")` | no | Geometry query: area of the faces with that material **(to verify)** |
| `FACES()` | no | Geometry query: number of faces **(to verify)** |
| `LARGEST(value1, value2, ...valueN)` | no | Probably the same as `MAX` **(to verify)** |
| `LAT()` | no | Latitude of the model's geolocation **(to verify)**; needs document data |
| … | | Rest of the list not captured |

## Functions we have that the screenshot does not show

`IF, AND, OR, NOT, MIN, MAX, INT, MOD, SIN, COS, TAN, ASIN, ACOS, ATAN, LEN, LEFT,
RIGHT, MID, CONCATENATE, VALUE, LOWER, UPPER, TRIM`. `MOD` (Excel semantics, sign of
the divisor) was added for grids from one `Copy` index; whether SketchUp lists it
**(to verify)**. They probably sit in categories further
down the list (logical, trigonometric, text); confirm when those are captured.

## Notes for implementing the missing ones

- **Pure math** (`EVEN, ODD, ISEVEN, ISODD, SIGN, EXP, LN, LOG10, POWER`) fits
  `formula.py` directly: no new data, only domain checks and the finite-result check.
- **`RAND`, `RANDBETWEEN`** make evaluation non-deterministic: every apply (options
  dialog, scale, definition edit, undo/redo re-apply) would move geometry. They need a
  decision first, for example a seed stored per instance. When SketchUp re-rolls the
  value is **(to verify)**.
- **Geometry queries** (`EDGES, FACES, FACEAREA`) and **document data** (`LAT`) need
  information that `formula`/`evaluate` must not fetch themselves (no IngeTrazo
  imports). They would have to arrive through the `lookup` callback from `binding`,
  which is a change to `docs/contract.md` first.
- **`CURRENT`** depends on what "current" means in SketchUp (stored value versus the
  value after a user edit); settle that before choosing an implementation.
