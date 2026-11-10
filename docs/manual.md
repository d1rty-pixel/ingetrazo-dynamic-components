# Manual

How to use Dynamic Components. For how it works inside see [DESIGN.md](DESIGN.md).

## Concepts

- A **dynamic component** is a component instance whose parts are laid out by **formulas**. The component and each of its parts have **attributes**.
- The **definition** (the attributes and formulas) is shared by every instance made from it; what a user changed in the options (**overrides**) belongs to one instance.
- Lengths are in the units of IngeTrazo (metres in the file), angles in degrees.
- Everything runs in the undo history: every change is one step.

## Making a component dynamic

Right-click a component instance → **Make Dynamic**. The tab shows its parts (the groups inside it) with the attributes a part always has: `X`, `Y`, `Z`, `LenX`, `LenY`, `LenZ`, `RotX`, `RotY`, `RotZ`, `Hidden`, `Material`, `Copies`.

The component's own `LenX/LenY/LenZ` are its size; the other attributes of a part are relative to the component.

## The Dynamic Components tab

The tab is in the side tray (closed by default: Window → Panels). It shows the selected dynamic instance.

- **Options**: the values users may change. Each change is one undo step; ↺ goes back to the default. **Component Options…** in the context menu opens this.
- **Bake** freezes the instance as it is now into a plain component. Cutters and hidden parts are removed, and the generated geometry (holes, grooves) stays.
- **One section per part**: click an attribute to edit its label, type, formula, who may see or edit it, limits and choices. A change is applied when you leave the field (Tab moves on), for every instance of the definition; one undo step each.

While a dynamic component is open for editing (double-click into it), the tab shows it read-only; leave it to change options or attributes.

## Attributes

An attribute has a **name**, a **label**, a **type**, a default **value** and optionally a **formula**.

| Type | Value |
|---|---|
| *Length* | a length (clamped to the limits) |
| *Number* | a decimal number |
| *Whole number* | an integer |
| *Yes / No* | true or false |
| *Text* | text |
| *Choice* | one of a list of options |
| *Material* | the name of a material of the document |

**Access** says what the user sees:

| Access | Meaning |
|---|---|
| *Hidden from users* | not shown; a helper for formulas |
| *Shown, read-only* | shown as text |
| *Users can edit* | the user types a value |
| *Users pick from a list* | the user picks one of the options (`["label", value]` pairs) |
| *Shown as a warning* | a computed text shown as a warning while it is not empty |

A formula wins over what the user typed: a formula attribute shows its computed value. The exceptions are the component's own `LenX/LenY/LenZ` and `X/Y/Z`, which come from scaling or moving the instance.

Limits (**min**, **max**) clamp what the user types.

### The attributes every part has

| Attribute | Meaning |
|---|---|
| `X`, `Y`, `Z` | position of the part in the component |
| `LenX`, `LenY`, `LenZ` | size of the part |
| `RotX`, `RotY`, `RotZ` | rotation in degrees (applied as Z·Y·X) |
| `Hidden` | the part is not shown (and, for a cutter, does not cut) |
| `Material` | the name of a material to paint the part with |
| `Copies` | number of **extra** copies of the part |
| `Copy` | (read only) the index of the copy being computed: 0 for the part, 1, 2, … for the copies |

A part with `Copies = 3` is shown four times.

## Formulas

A formula starts with `=`. Examples:

```
=Parent!LenX - 2*Thickness
=IF(Plinth, Plinth_H, 0)
=Shelf!Z + Copy*Gap
="Width: " & ROUND(LenX*100, 0) & " cm"
```

- **Names** are not case sensitive. `Parent!Name` is an attribute of the component, `Part!Name` an attribute of another part (by its name), `Name` an attribute of the same part.
- **Operators:** `+ - * / ^ &` (join text), `= <> < > <= >=`, parentheses. Texts are in `"double"` or `'single'` quotes; double a quote to write one.
- **Functions:** `IF AND OR NOT CHOOSE`, `MIN MAX ABS ROUND FLOOR CEILING INT MOD SQRT`, `SIN COS TAN ASIN ACOS ATAN RADIANS DEGREES PI`, `LEN LEFT RIGHT MID CONCATENATE VALUE LOWER UPPER TRIM`. Trigonometry works in degrees. `FLOOR` and `CEILING` take an optional second argument (the step, default 1). `MOD` has the sign of the divisor (like Excel). See [sketchup-functions.md](sketchup-functions.md) for SketchUp's list against ours.
- Formulas are checked as you type (insert menu and completion for references and functions). A formula that fails shows its error under the attribute and keeps its last good value, so a typo never breaks the component.
- **Limits:** a formula has at most 4096 characters; depth, steps, texts and copies are limited too, so that a document cannot freeze the program.

### Repeating parts

`Copies` repeats a part. In the formulas of the part, `Copy` is the index of the copy, so a row of posts is `X = Copy*Spacing`. A grid is made from one index: `X = MOD(Copy, Columns)*W`, `Y = FLOOR(Copy/Columns, 1)*D`.

## Options layout

An attribute can name a **section** (options with the same section are shown together under that heading) and a **Show if** formula (the option is shown only while it is true, e.g. `=Plinth` or `=Shelf_Mode="fixed"`). A *Show if* that fails leaves the row visible and reports its error. The access **Shown as a warning** makes a computed text appear as a warning while it is not empty.

## Scaling

Scaling an instance with the Scale tool lays its parts out live while you drag (boards keep their thickness) and stores the new size on release, in `LenX/LenY/LenZ`. Parts always follow the definition: a part moved by hand inside the component goes back to where its attributes put it.

## Adding and removing parts

A group cannot be made *inside* a component (IngeTrazo keeps a component's parts as they are). Make it outside, right-click it and choose **Add to Dynamic Component…**: a small dialog lists the dynamic components that can take it, and the group keeps its place in the model (one undo step). A group already sitting in a dynamic component without being a part offers **Add as Part of “…”** in the context menu and **Add as part** in the tab.

A part deleted inside the component disappears from the tab, which offers **Remove from definition**.

## Generated parts and cutters (real holes)

Each part's section starts with **Geometry** and **Cuts into**.

- **Geometry: Board with holes, pockets and grooves** (`board@1`): the part is no longer stretched; its mesh is built at its size (`LenX/Y/Z`), so holes stay round and keep their spacing when the component grows.
- **Cuts into: a part**: this part becomes a *cutter*. It is never drawn; its box is cut out of the other part where they meet. Its position, `Copies` and `Hidden` (= cut off) come from formulas as usual.

What the cutter makes depends on its shape and where it meets the board:

| Cutter | Makes |
|---|---|
| a cylinder (more than 6 faces) that enters through one face | a round hole (blind) or a through hole (through two opposite faces) |
| a box that stays inside a face | a rectangular pocket or opening |
| a box that runs along the whole length of the board from one face | a groove |

Rules: a cut must be aligned with the board (rotations by multiples of 90° are fine) and may not touch or overlap another cut. A groove must stay clear of the board's sides across it (otherwise it would be a rebate); all grooves of a board run the same way from the same face; holes and pockets in that face must stay clear of the groove. Notches over a corner are not possible. Limits: 2000 cuts and 200 000 faces per board. Anything that cannot be made is reported in the part's section and skipped; the other cuts still happen.

The holes are ordinary geometry, saved in the file and exported. A generated part edited by hand (push/pull inside the board) is left alone: the tab says so and offers **Regenerate** (the edits are lost). While you drag the Scale tool, generated parts are stretched; they are rebuilt when you release. **Bake** keeps the holes and removes the cutters.

The example model [system32-cabinet](../models/system32-cabinet/README.md) is built from exactly these pieces.

## Sharing

A dynamic component is shared as an `.igz` file: open it, or copy the component into another document. The definition travels with the instance (a copy is stored on it), so it keeps working there. If the other document already has a *different* definition under the same id, that document's own one wins.

The extension has to be installed to edit the options. Without it the component is still there, with its real geometry (holes included), but behaves like a plain component. A generator is code of the extension; a document only names it (`board@1`). If a document names one that the installed extension does not know, the tab says "(not installed)" and the part keeps its last mesh.

## Language

The tab follows IngeTrazo's interface language. German, Spanish and French are included; English is the source and the fallback (any other language, and any string a catalog lacks, shows in English). Another language is one file, `dynamic_components/locale/<code>.json` (`{"English text": "translation"}`). Labels you type into a definition are yours and are not translated.

## Limits

- Only one level of parts: nested dynamic components are not evaluated.
- Scaling an instance and the move of that scale into `LenX/Y/Z` are two undo steps.
- The rotation order (`RotZ·RotY·RotX`) and the meaning of `Copies` (N extra copies) follow SketchUp from memory and are not verified against real files.
- No `.skp` import of SketchUp's dynamic attributes yet.
- Interplay with Newton's *Keep the pose on reset* is not handled yet.
- Generated boards: no notches over a corner, no rotated cutters; groove only along a whole board.
- Formulas: at most 256 parts per component, 256 attributes per part, 1000 copies per part.
