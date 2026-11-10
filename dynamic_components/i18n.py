"""Translations: English is the source and the key, as in the host.

Catalogs are ``locale/<lang>.json``: flat ``{english: translation}`` maps. The
language is the host's interface language (``core.i18n.current_language``),
read when a string is translated, so a language switch needs no restart of
this extension; outside the host it is English.
"""
from __future__ import annotations

import json
from pathlib import Path

from .messages import Msg, N_  # noqa: F401 - N_ is re-exported for the UI

_DIR = Path(__file__).resolve().parent / "locale"
_catalogs: dict[str, dict[str, str]] = {}
_override: list = []        # tests set a language without the host


def language() -> str:
    if _override:
        return _override[-1]
    try:
        from core.i18n import current_language
        return current_language() or "en"
    except Exception:  # noqa: BLE001 - outside the host
        return "en"


def set_language(lang) -> None:
    """Force a language (tests); ``None`` follows the host again."""
    _override.clear()
    if lang:
        _override.append(lang)


def catalog(lang: str) -> dict[str, str]:
    if lang in _catalogs:
        return _catalogs[lang]
    data: dict[str, str] = {}
    candidates = [lang]
    base = lang.replace("_", "-").split("-")[0]
    if base != lang:
        candidates.append(base)
    for code in candidates:
        path = _DIR / f"{code}.json"
        if code != "en" and path.is_file():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                data = {str(k): str(v) for k, v in raw.items() if v}
            except (OSError, ValueError):
                data = {}
            break
    _catalogs[lang] = data
    return data


def available() -> list[str]:
    return sorted({"en"} | {p.stem for p in _DIR.glob("*.json")})


def tr(text: str, /, **kwargs) -> str:
    """``text`` in the interface language, ``{fields}`` filled from kwargs."""
    out = catalog(language()).get(text, text)
    if kwargs:
        try:
            return out.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            try:
                return text.format(**kwargs)
            except (KeyError, IndexError, ValueError):
                return text
    return out


def tr_msg(message) -> str:
    """A Msg in the interface language (its parameters too, when they are
    messages or marked words); anything else as text."""
    if not isinstance(message, Msg):
        return "" if message is None else str(message)
    table = catalog(language())
    params = {}
    for key, value in message.params.items():
        if isinstance(value, Msg):
            params[key] = tr_msg(value)
        elif isinstance(value, str):
            params[key] = table.get(value, value)
        else:
            params[key] = value
    template = table.get(message.template, message.template)
    try:
        return template.format(**params) if params else template
    except (KeyError, IndexError, ValueError):
        return str(message)


def tr_error(exc) -> str:
    """The message of an exception, translated when it carries a Msg."""
    msg = getattr(exc, "msg", None)
    if isinstance(msg, Msg):
        return tr_msg(msg)
    args = getattr(exc, "args", ())
    if args and isinstance(args[0], Msg):
        return tr_msg(args[0])
    return str(exc)
