"""Cell value -> database value conversion, one function per configured type.

Shared by validator.py (dry run: does every cell fit its configured type?) and
executor.py (the real load), so both judge a value identically.
"""
import datetime as dt
import re

TYPES = ("text", "numeric", "integer", "date", "timestamp", "boolean")

MONEY = re.compile(r"[^0-9.\-]")

DATE_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%d-%m-%Y",
                "%d/%m/%Y", "%d-%b-%Y", "%d %b %Y", "%Y/%m/%d",
                "%A, %d %B %Y")

BLANKS = ("", "-", "--", "NA", "N/A")


def to_number(value):
    """'₹1,234.50' -> 1234.5, '(120.00)' -> -120.0, '18%' -> 18.0."""
    if value is None or isinstance(value, (int, float)):
        return value
    text = MONEY.sub("", str(value).replace("(", "-"))
    if text in ("", "-", "."):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def to_date(value, with_time: bool):
    """Excel date/text -> 'YYYY-MM-DD[ HH:MM:SS]'. Raises ValueError on junk."""
    if isinstance(value, (dt.datetime, dt.date)):
        if with_time and isinstance(value, dt.datetime):
            return value.isoformat(sep=" ")
        return str(value)[:10]
    text = str(value or "").strip()
    if text in BLANKS:
        return None
    for fmt in DATE_FORMATS:
        try:
            parsed = dt.datetime.strptime(text, fmt)
        except ValueError:
            continue
        return parsed.isoformat(sep=" ") if with_time else parsed.date().isoformat()
    raise ValueError(f"{text!r} is not a date")


def cast(value, dtype: str):
    """Convert one cell for its configured data_type. Raises ValueError on junk."""
    if dtype in ("numeric", "integer"):
        number = to_number(value)
        return int(number) if dtype == "integer" and number is not None else number
    if dtype in ("date", "timestamp"):
        return to_date(value, dtype == "timestamp")
    if dtype == "boolean":
        text = str(value or "").strip().lower()
        if text in ("y", "yes", "true", "1"):
            return True
        if text in ("n", "no", "false", "0"):
            return False
        return None
    text = str(value).strip() if value is not None else None
    return text or None
