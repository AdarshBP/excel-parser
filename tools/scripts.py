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
    """'hello world' -> 'HELLO WORLD'"""
    if not isinstance(v, str):
        raise ScriptError(f"uppercase expects text, got {type(v).__name__}")
    return v.upper()

def _lowercase(v):
    """'Hello World' -> 'hello world'"""
    if not isinstance(v, str):
        raise ScriptError(f"lowercase expects text, got {type(v).__name__}")
    return v.lower()

def _titlecase(v):
    """'hello world' -> 'Hello World'"""
    if not isinstance(v, str):
        raise ScriptError(f"titlecase expects text, got {type(v).__name__}")
    return v.title()

def _trim(v):
    """'  hello  ' -> 'hello'"""
    if not isinstance(v, str):
        raise ScriptError(f"trim expects text, got {type(v).__name__}")
    return v.strip()

def _strip_spaces(v):
    """'hello world' -> 'helloworld'"""
    if not isinstance(v, str):
        raise ScriptError(f"strip_spaces expects text, got {type(v).__name__}")
    return re.sub(r"\s+", "", v)

def _digits_only(v):
    """'INV-001-AB' -> '001'"""
    if not isinstance(v, str):
        raise ScriptError(f"digits_only expects text, got {type(v).__name__}")
    return re.sub(r"[^0-9]", "", v)

def _letters_only(v):
    """'Order-123' -> 'Order'"""
    if not isinstance(v, str):
        raise ScriptError(f"letters_only expects text, got {type(v).__name__}")
    return re.sub(r"[^a-zA-Z]", "", v)

def _alphanum_only(v):
    """'Order #123!' -> 'Order123'"""
    if not isinstance(v, str):
        raise ScriptError(f"alphanum_only expects text, got {type(v).__name__}")
    return re.sub(r"[^a-zA-Z0-9]", "", v)

def _replace_newlines(v):
    """'line1\\nline2' -> 'line1 line2'"""
    if not isinstance(v, str):
        raise ScriptError(f"replace_newlines expects text, got {type(v).__name__}")
    return re.sub(r"[\r\n]+", " ", v).strip()

def _collapse_spaces(v):
    """'hello    world' -> 'hello world'"""
    if not isinstance(v, str):
        raise ScriptError(f"collapse_spaces expects text, got {type(v).__name__}")
    return re.sub(r"\s+", " ", v).strip()

def _remove_punctuation(v):
    """'Hello, World!' -> 'Hello World'"""
    if not isinstance(v, str):
        raise ScriptError(f"remove_punctuation expects text, got {type(v).__name__}")
    return re.sub(r"[^\w\s]", "", v)

def _first_word(v):
    """'John Smith' -> 'John'"""
    if not isinstance(v, str):
        raise ScriptError(f"first_word expects text, got {type(v).__name__}")
    parts = v.strip().split()
    return parts[0] if parts else ""

def _last_word(v):
    """'John Smith' -> 'Smith'"""
    if not isinstance(v, str):
        raise ScriptError(f"last_word expects text, got {type(v).__name__}")
    parts = v.strip().split()
    return parts[-1] if parts else ""

def _left_10(v):
    """'ABCDEFGHIJKLMNOP' -> 'ABCDEFGHIJ'"""
    if not isinstance(v, str):
        raise ScriptError(f"left_10 expects text, got {type(v).__name__}")
    return v[:10]

def _right_10(v):
    """'ABCDEFGHIJKLMNOP' -> 'GHIJKLMNOP'"""
    if not isinstance(v, str):
        raise ScriptError(f"right_10 expects text, got {type(v).__name__}")
    return v[-10:] if len(v) >= 10 else v

def _slug(v):
    """'Hello World!' -> 'hello-world'"""
    if not isinstance(v, str):
        raise ScriptError(f"slug expects text, got {type(v).__name__}")
    s = re.sub(r"[^\w\s-]", "", v.lower().strip())
    return re.sub(r"[\s_]+", "-", s).strip("-")

# ── numeric scripts ──────────────────────────────────────────────────────

def _abs(v):
    """-120.5 -> 120.5"""
    if not isinstance(v, (int, float)):
        raise ScriptError(f"abs expects numeric, got {type(v).__name__}")
    return abs(v)

def _round_2(v):
    """3.14159 -> 3.14"""
    if not isinstance(v, (int, float)):
        raise ScriptError(f"round_2 expects numeric, got {type(v).__name__}")
    return round(float(v), 2)

def _round_0(v):
    """3.7 -> 4.0"""
    if not isinstance(v, (int, float)):
        raise ScriptError(f"round_0 expects numeric, got {type(v).__name__}")
    return round(float(v), 0)

def _floor(v):
    """3.9 -> 3"""
    if not isinstance(v, (int, float)):
        raise ScriptError(f"floor expects numeric, got {type(v).__name__}")
    return int(math.floor(v))

def _ceil(v):
    """3.1 -> 4"""
    if not isinstance(v, (int, float)):
        raise ScriptError(f"ceil expects numeric, got {type(v).__name__}")
    return int(math.ceil(v))

def _negate(v):
    """100 -> -100"""
    if not isinstance(v, (int, float)):
        raise ScriptError(f"negate expects numeric, got {type(v).__name__}")
    return -v

def _pct_to_fraction(v):
    """18.0 -> 0.18 (divide by 100)"""
    if not isinstance(v, (int, float)):
        raise ScriptError(f"pct_to_fraction expects numeric, got {type(v).__name__}")
    return v / 100.0

def _fraction_to_pct(v):
    """0.18 -> 18.0 (multiply by 100)"""
    if not isinstance(v, (int, float)):
        raise ScriptError(f"fraction_to_pct expects numeric, got {type(v).__name__}")
    return v * 100.0

def _round_1(v):
    """3.456 -> 3.5"""
    if not isinstance(v, (int, float)):
        raise ScriptError(f"round_1 expects numeric, got {type(v).__name__}")
    return round(float(v), 1)

def _clamp_0(v):
    """-5 -> 0 (negative values become 0)"""
    if not isinstance(v, (int, float)):
        raise ScriptError(f"clamp_0 expects numeric, got {type(v).__name__}")
    return max(0, v)

# ── date scripts ─────────────────────────────────────────────────────────

def _date_only(v):
    """'2026-08-02T19:45:00' -> '2026-08-02'"""
    if not isinstance(v, str):
        raise ScriptError(f"date_only expects a date string, got {type(v).__name__}")
    return v[:10]

def _year_month(v):
    """'2026-08-02' -> '2026-08'"""
    if not isinstance(v, str):
        raise ScriptError(f"year_month expects a date string, got {type(v).__name__}")
    return v[:7]

def _year_only(v):
    """'2026-08-02' -> '2026'"""
    if not isinstance(v, str):
        raise ScriptError(f"year_only expects a date string, got {type(v).__name__}")
    return v[:4]

# ── guard scripts ────────────────────────────────────────────────────────

def _not_null(v):
    """Raises an error if the value is NULL."""
    if v is None:
        raise ScriptError("value is NULL but script requires it to be non-null")
    return v

def _not_empty(v):
    """Raises an error if the value is NULL or an empty string."""
    if v is None or (isinstance(v, str) and not v.strip()):
        raise ScriptError("value is empty but script requires a non-empty value")
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
    "replace_newlines": _replace_newlines,
    "collapse_spaces": _collapse_spaces,
    "remove_punctuation": _remove_punctuation,
    "first_word": _first_word,
    "last_word": _last_word,
    "left_10": _left_10,
    "right_10": _right_10,
    "slug": _slug,
    # numeric
    "abs": _abs,
    "round_2": _round_2,
    "round_1": _round_1,
    "round_0": _round_0,
    "floor": _floor,
    "ceil": _ceil,
    "negate": _negate,
    "pct_to_fraction": _pct_to_fraction,
    "fraction_to_pct": _fraction_to_pct,
    "clamp_0": _clamp_0,
    # date
    "date_only": _date_only,
    "year_month": _year_month,
    "year_only": _year_only,
    # guard
    "not_null": _not_null,
    "not_empty": _not_empty,
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
