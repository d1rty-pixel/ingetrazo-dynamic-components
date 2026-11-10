# Frequently asked questions

## Can I give a dynamic component to someone else?

Yes: send the `.igz`, or copy the component into their document. The definition travels with it. They need the extension installed to change the options; without it they still see the component with its real geometry, but it behaves like a plain one. See [Sharing](manual.md#sharing).

## I copied a component into another document and the options are gone.

The extension has to be installed in IngeTrazo, and loaded (restart after installing). A component made with an older version of the extension, before components carried their definition, does not bring it along: open the original document and make the component again, or copy it from a file written by this version.

## Why are the holes oval while I scale?

While the Scale tool drags, generated parts (boards with holes) are stretched to keep the view fast. They are rebuilt when you release the mouse, with round holes and their real spacing.

## I pushed/pulled a board and now the tab says "edited by hand".

A generated part you edited by hand is left alone, so your work is not lost. **Regenerate** in the tab discards your edits and builds it from the definition again; **Bake** keeps them.

## How do I change one compartment of a cabinet on its own?

Dynamic components lay every copy out the same way. To change a part of the result, **Bake** the cabinet (it becomes plain boards) and edit it. Baking is one undo step.

## Why does a formula show an error but the value still works?

A failing formula keeps its last good value, so a typo while you are typing never breaks the component. The error is shown under the attribute.

## Does it import SketchUp's dynamic components?

Not yet. The formula language follows SketchUp's, so formulas can be typed in by hand; see [sketchup-functions.md](sketchup-functions.md) for what is covered.

## Can a document run code?

No. A document holds formulas, which run in a small interpreter of their own, and the name of a generator. The generators are code of the extension. Nothing from a document is ever executed as Python.
