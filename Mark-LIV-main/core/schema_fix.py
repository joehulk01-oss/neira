"""
Gemini function-declaration schema sanitizer.

The Live API (BidiGenerateContentRequest) validates tool schemas strictly:
every ``"type": "ARRAY"`` node MUST carry an ``items`` schema. A single bad
node anywhere in the tree makes the whole setup message fail with:

    APIError: 1007 ... function_declarations[N].parameters.properties[steps]
    .items: missing field.

That error was previously misread by main.py as an invalid API key, popping
the "INITIALISATION REQUIRED" overlay in an endless loop even though the key
was fine (auth had already succeeded — the WebSocket was open).

``sanitize_schema`` repairs the tree in place so declarations built by skills,
plugins, or hand-edited files always satisfy the API:

  * ARRAY without a valid ``items``              -> ``items = {"type": "STRING"}``
  * OBJECT without ``properties``                -> ``properties = {}``
  * ``required`` entries missing from properties -> dropped
  * empty ``required``                           -> removed
  * ``items`` on a non-ARRAY node                -> removed
  * ``properties``/``required`` on a non-OBJECT  -> removed
  * unknown / invalid ``type`` names             -> ``"STRING"``
  * malformed ``enum``                           -> removed
"""
from __future__ import annotations

from typing import Any

# The exact Type enum the Gemini API accepts (uppercase).
_TYPES = {"STRING", "NUMBER", "INTEGER", "BOOLEAN", "ARRAY", "OBJECT"}


def _norm_type(value: Any) -> str:
    s = str(value or "").strip().upper()
    return s if s in _TYPES else "STRING"


def sanitize_schema(schema: Any) -> dict:
    """Recursively repair `schema` so Gemini's strict validator accepts it.

    Mutates and returns the dict where possible; a non-dict input is replaced
    with a minimal valid string schema (the API rejects bare non-dict nodes).
    """
    if not isinstance(schema, dict):
        return {"type": "STRING"}

    stype = _norm_type(schema.get("type"))

    if stype == "ARRAY":
        items = schema.get("items")
        if isinstance(items, dict):
            schema["items"] = sanitize_schema(items)
        else:
            schema["items"] = {"type": "STRING"}
    else:
        schema.pop("items", None)          # items is only legal on ARRAY

    if stype == "OBJECT":
        props = schema.get("properties")
        if not isinstance(props, dict):
            props = {}
            schema["properties"] = props
        else:
            for key, sub in list(props.items()):
                props[key] = sanitize_schema(sub)

        req = schema.get("required")
        if isinstance(req, list):
            req = [r for r in req if isinstance(r, str) and r in props]
            if req:
                schema["required"] = req
            else:
                schema.pop("required", None)
        else:
            schema.pop("required", None)
    else:
        schema.pop("properties", None)     # only legal on OBJECT
        schema.pop("required", None)

    if "enum" in schema:
        enum = schema.get("enum")
        if not (isinstance(enum, list) and enum
                and all(isinstance(e, str) for e in enum)):
            schema.pop("enum", None)

    schema["type"] = stype
    return schema


def sanitize_declarations(decls: Any) -> Any:
    """Sanitize the ``parameters`` schema of every tool declaration in `decls`.

    Accepts and returns the same list shape main.py builds
    (``TOOL_DECLARATIONS + action + plugin declarations``); non-dict entries
    pass through untouched.
    """
    if not isinstance(decls, list):
        return decls
    for d in decls:
        if isinstance(d, dict) and isinstance(d.get("parameters"), dict):
            d["parameters"] = sanitize_schema(d["parameters"])
    return decls
