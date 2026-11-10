# Known issues

Open points and limits. See also [Limits](manual.md#limits).

## Behaviour that is not verified against SketchUp

- The order of rotations (`RotZ·RotY·RotX`) and the meaning of `Copies` (N extra copies) follow SketchUp from memory and are not checked against real files.
- Several of SketchUp's functions are missing; the list is in [sketchup-functions.md](sketchup-functions.md). The screenshot it is based on shows only part of SketchUp's list.

## Scaling is two undo steps

Scaling an instance and the move of that scale into `LenX/Y/Z` are two undo steps.

## Components made before they carried their definition

A component made with a version before 0.1.0 does not carry its definition; copied into another document it behaves like a plain component. Make it again with a current version.

## One level of parts

Parts of a dynamic component are its direct groups. A dynamic component inside a dynamic component is not evaluated.

## Generated boards

- No notches over a corner and no rotated cutters; a groove must run along a whole board and stay clear of the board's sides.
- A divider in the example cabinet has no groove for the back panel; it stops in front of the panel.
- A baked cabinet is plain boards: changing one compartment afterwards is a hand edit.

## Newton

Interplay with Newton's *Keep the pose on reset* is not handled yet.

## Translations

German, Spanish and French only; everything else shows in English. The translations of the UI were written with a machine and are not reviewed by native speakers.
