# Security Policy

## Supported versions

Only the latest [release](https://github.com/d1rty-pixel/ingetrazo-dynamic-components/releases) of Dynamic Components receives security fixes.

## Reporting a vulnerability

Please do not open a public issue. Use GitHub's private reporting instead: [Report a vulnerability](https://github.com/d1rty-pixel/ingetrazo-dynamic-components/security/advisories/new) (Security tab of this repository).

Include the extension version, the IngeTrazo version, your operating system and steps to reproduce. A minimal `.igz` file helps if the problem depends on a model.

You get a first response within 7 days. Fixes are released first; the advisory is published afterwards.

## Scope

A dynamic component's definition (formulas, attributes) is stored in the `.igz` and comes from documents the extension did not write. It is treated as untrusted input: formulas run in an interpreter of their own (no `eval`, `exec` or `compile`), with limits on size, depth, steps, copies and faces, and a failing formula keeps the last good value. Generators are Python code of the extension; a document only names one.

In scope:

- the formula interpreter (`formula.py`), the spec validation (`spec.py`), the evaluation (`evaluate.py`) and the geometry builder (`geometry.py`, `generators.py`);
- loading of definitions and instance data stored in `.igz` files (`scene.plugin_data["dynamic_components"]`, `group.ext["dynamic_components"]`), including definitions that travel with a pasted component;
- `scripts/package.py` and the release zip.

Out of scope:

- vulnerabilities in IngeTrazo or Python themselves; please report those upstream;
- issues that require local code execution as the same user, since an extension runs with that user's rights anyway.
