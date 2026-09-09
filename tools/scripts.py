"""Predefined cell transformation scripts.

Each script is a pure function: value in, value out, raise ScriptError on
failure. Scripts run AFTER type casting, so they receive typed values (str,
int, float, date string) not raw Excel cells.

Multiple scripts are chained with ``|``: ``trim|uppercase`` runs trim first,
then uppercase on the result.

    from scripts import apply
    apply("  Hello World  ", "trim|uppercase")   # -> "HELLO WORLD"
    apply(-11.25, "abs|round_2")                 # -> 11.25
"""
import math
import re


class ScriptError(Exception):
    """A script could not transform the value."""


# ── text scripts ─────────────────────────────────────────────────────────

def _uppercase(v):
    if not isinstance(v, str):
        raise ScriptError(f"uppercase expects text, got {type(v).__name__}")
    return v.upper()

def _lowercase(v):
    if not isinstance(v, str):
        raise ScriptError(f"lowercase expects text, got {type(v).__name__}")
    return v.lower()

def _titlecase(v):
    if not isinstance(v, str):
        raise ScriptError(f"titlecase expects text, got {type(v).__name__}")
    return v.title()

def _trim(v):
    if not isinstance(v, str):
        raise ScriptError(f"trim expects text, got {type(v).__name__}")
    return v.strip()

def _strip_spaces(v):
    if not isinstance(v, str):
        raise ScriptError(f"strip_spaces expects text, got {type(v).__name__}")
    return re.sub(r"\s+", "", v)

def _digits_only(v):
    if not isinstance(v, str):
        raise ScriptError(f"digits_only expects text, got {type(v).__name__}")
    return re.sub(r"[^0-9]", "", v)

def _letters_only(v):
    if not isinstance(v, str):
        raise ScriptError(f"letters_only expects text, got {type(v).__name__}")
    return re.sub(r"[^a-zA-Z]", "", v)

def _alphanum_only(v):
    if not isinstance(v, str):
        raise ScriptError(f"alphanum_only expects text, got {type(v).__name__}")
    return re.sub(r"[^a-zA-Z0-9]", "", v)

# ── numeric scripts ──────────────────────────────────────────────────────

def _abs(v):
    if not isinstance(v, (int, float)):
        raise ScriptError(f"abs expects numeric, got {type(v).__name__}")
    return abs(v)

def _round_2(v):
    if not isinstance(v, (int, float)):
        raise ScriptError(f"round_2 expects numeric, got {type(v).__name__}")
    return round(float(v), 2)

def _round_0(v):
    if not isinstance(v, (int, float)):
        raise ScriptError(f"round_0 expects numeric, got {type(v).__name__}")
    return round(float(v), 0)

def _floor(v):
    if not isinstance(v, (int, float)):
        raise ScriptError(f"floor expects numeric, got {type(v).__name__}")
    return int(math.floor(v))

def _ceil(v):
    if not isinstance(v, (int, float)):
        raise ScriptError(f"ceil expects numeric, got {type(v).__name__}")
    return int(math.ceil(v))

def _negate(v):
    if not isinstance(v, (int, float)):
        raise ScriptError(f"negate expects numeric, got {type(v).__name__}")
    return -v

# ── date scripts ─────────────────────────────────────────────────────────

def _date_only(v):
    if not isinstance(v, str):
        raise ScriptError(f"date_only expects a date string, got {type(v).__name__}")
    return v[:10]

def _year_month(v):
    if not isinstance(v, str):
        raise ScriptError(f"year_month expects a date string, got {type(v).__name__}")
    return v[:7]

# ── guard scripts ────────────────────────────────────────────────────────

def _not_null(v):
    if v is None:
        raise ScriptError("value is NULL but script requires it to be non-null")
    return v

# ── registry ─────────────────────────────────────────────────────────────

SCRIPTS = {
    # text
    "uppercase": _uppercase,
    "lowercase": _lowercase,
    "titlecase": _titlecase,
    "trim": _trim,
    "strip_spaces": _strip_spaces,
    "digits_only": _digits_only,
    "letters_only": _letters_only,
    "alphanum_only": _alphanum_only,
    # numeric
    "abs": _abs,
    "round_2": _round_2,
    "round_0": _round_0,
    "floor": _floor,
    "ceil": _ceil,
    "negate": _negate,
    # date
    "date_only": _date_only,
    "year_month": _year_month,
    # guard
    "not_null": _not_null,
}


def validate_spec(spec: str) -> list[str]:
    """Check that every script name in a spec is known. Returns unknown names."""
    if not spec:
        return []
    unknown = []
    for name in spec.split("|"):
        name = name.strip()
        if name and name not in SCRIPTS:
            unknown.append(name)
    return unknown


def apply(value, spec: str):
    """Apply one or more scripts to a value. Returns the transformed value.

    Skips if value is None (unless the script is not_null).
    Raises ScriptError on any failure.
    """
    if not spec:
        return value
    for name in spec.split("|"):
        name = name.strip()
        if not name:
            continue
        if value is None and name != "not_null":
            return None
        fn = SCRIPTS.get(name)
        if fn is None:
            raise ScriptError(f"unknown script '{name}'")
        value = fn(value)
    return value
