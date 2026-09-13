"""Stage 1 - validate the configuration (and the source workbook against it).

    python validator.py config.xlsx                       # config only
    python validator.py config.xlsx source.xlsx           # config + that file
    python validator.py config.xlsx source.xlsx --ddl schema.postgres.sql --dialect postgres

Nothing is written to a database here. The validator answers one question:
"can this pair of workbooks be pushed?" - and, when the answer is yes, it can
write the DDL that executor.py will apply.

Exit code 0 = safe to push (warnings may still be printed), 1 = errors found.

For an application later: call `validate()` and `render_ddl()` directly. Both
are pure functions - `validate()` returns a list of `Issue` records and prints
nothing, so a UI can group them however it likes.
"""
import argparse
import sys
from collections import namedtuple
from pathlib import Path

import openpyxl
from openpyxl.utils import column_index_from_string

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import IDENTIFIER  # noqa: E402
import scripts  # noqa: E402
from scripts import validate_spec as validate_script  # noqa: E402
from values import TYPES as VALUE_TYPES, cast  # noqa: E402

# severity: "error" blocks the push, "warning" is worth reading first.
Issue = namedtuple("Issue", "severity where message")

Target = namedtuple("Target", "target database db_schema prefix id_type")
DEFAULTS = Target("sqlite", None, None, "", "integer")
TARGET_SETTINGS = ("target", "database", "db_schema", "table_prefix", "id_type")
ID_TYPES = ("integer", "uuid")

SHEET_FIELDS = ("table_name", "sheet_name", "layout", "header_row",
                "data_start_row", "data_end_row", "row_filter", "active", "notes")
COLUMN_FIELDS = ("table_name", "source_ref", "source_header", "column_name",
                 "data_type", "nullable", "is_key", "column_order",
                 "references", "null_default", "date_format")
LAYOUTS = ("table", "key_value")
LINEAGE = ("file_id", "sheet_name", "source_row_num")

DDL_TYPES = {
    "postgres": {
        "text": "TEXT", "numeric": "NUMERIC(18,4)", "integer": "INTEGER",
        "date": "DATE", "timestamp": "TIMESTAMP", "boolean": "BOOLEAN",
        "id": "BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY", "fk": "BIGINT",
    },
    "sqlite": {
        "text": "TEXT", "numeric": "NUMERIC", "integer": "INTEGER",
        "date": "TEXT", "timestamp": "TEXT", "boolean": "INTEGER",
        "id": "INTEGER PRIMARY KEY AUTOINCREMENT", "fk": "INTEGER",
    },
}

# id_type = uuid: the key is a UUID the executor generates, so the same value
# works on both targets and no database extension is needed.
UUID_TYPES = {
    "postgres": {"id": "UUID PRIMARY KEY", "fk": "UUID"},
    "sqlite": {"id": "TEXT PRIMARY KEY", "fk": "TEXT"},
}


def ddl_types(dialect: str, id_type: str = "integer") -> dict:
    """The dialect's type map, with the key columns switched to UUID if asked."""
    types = dict(DDL_TYPES[dialect])
    if str(id_type or "integer").strip().lower() == "uuid":
        types.update(UUID_TYPES[dialect])
    return types

CONTROL_DDL = """-- Audit of every load: which file was loaded, with which config, into which table.
-- file_sha256 is unique so re-loading identical content is refused.
CREATE TABLE {p}load_config_audit (
    audit_id         {id},
    file_id          {text} NOT NULL,
    file_name        {text} NOT NULL,
    file_sha256      {text} NOT NULL,
    source_ref       {text},
    config_ref       {text},
    table_name       {text} NOT NULL,
    sheet_name       {text} NOT NULL,
    header_row       {integer},
    data_start_row   {integer},
    data_end_row     {integer},
    column_count     {integer},
    row_count        {integer},
    loaded_at        {timestamp} NOT NULL
);
CREATE UNIQUE INDEX ux_{p}audit_sha ON {p}load_config_audit (file_sha256, table_name);
"""


# ---------------------------------------------------------------- reading


def read_config(path: Path):
    """Configuration workbook -> (active sheet_config rows, columns per table).

    Inactive rows are dropped here, so everything downstream sees only what is
    meant to be built and loaded.
    """
    wb = openpyxl.load_workbook(path, data_only=True)
    for required in ("sheet_config", "column_config"):
        if required not in wb.sheetnames:
            raise SystemExit(f"{path.name} has no '{required}' worksheet")
    sheets, columns = [], {}

    rows = list(wb["sheet_config"].iter_rows(values_only=True))
    head = [str(h).strip() for h in rows[0]]
    for row in rows[1:]:
        rec = dict(zip(head, row))
        if not rec.get("table_name"):
            continue
        if str(rec.get("active", "Y")).strip().upper() != "Y":
            continue
        sheets.append(rec)

    rows = list(wb["column_config"].iter_rows(values_only=True))
    head = [str(h).strip() for h in rows[0]]
    for row in rows[1:]:
        rec = dict(zip(head, row))
        if not rec.get("table_name") or not rec.get("column_name"):
            continue
        columns.setdefault(rec["table_name"], []).append(rec)
    for table in columns:
        columns[table].sort(key=lambda r: r.get("column_order") or 0)
    return sheets, columns


def read_target(path: Path) -> dict:
    """The optional `target_config` sheet -> {setting: value}.

    It says *where* the data goes - target, database, schema, table prefix.
    Never credentials: host, user and password stay in the environment/.env.
    Returns {} when the sheet is absent, so older workbooks keep working.
    """
    wb = openpyxl.load_workbook(path, data_only=True)
    if "target_config" not in wb.sheetnames:
        return {}
    settings = {}
    rows = list(wb["target_config"].iter_rows(values_only=True))
    head = [str(h).strip().lower() for h in rows[0]]
    for row in rows[1:]:
        rec = dict(zip(head, row))
        key = str(rec.get("setting") or "").strip().lower()
        value = rec.get("value")
        value = str(value).strip() if value is not None else ""
        if key and value:
            settings[key] = value
    return settings


def resolve_target(config: Path, target=None, database=None, prefix=None,
                   id_type=None) -> Target:
    """Merge the workbook's `target_config` with the command line.

    Precedence: command line > target_config > built-in default. Credentials are
    not part of this - PostgreSQL still authenticates from the environment/.env.
    """
    settings = read_target(config)
    return Target(
        target=(target or settings.get("target") or DEFAULTS.target).strip().lower(),
        database=database or settings.get("database") or DEFAULTS.database,
        db_schema=settings.get("db_schema") or DEFAULTS.db_schema,
        prefix=(prefix if prefix is not None else settings.get("table_prefix")) or "",
        id_type=(id_type or settings.get("id_type") or DEFAULTS.id_type).strip().lower(),
    )


def _ref_kind(source_ref) -> tuple:
    """Parse 'kind:payload' -> (kind, payload). Returns ('', '') on bad input."""
    text = str(source_ref or "").strip()
    kind, sep, payload = text.partition(":")
    if not sep:
        return ("", "")
    return (kind.strip().lower(), payload.strip())


def is_const_ref(source_ref) -> bool:
    """True if source_ref is a 'const:<value>' constant."""
    return _ref_kind(source_ref)[0] == "const"


def const_value(source_ref) -> str:
    """'const:adarsh' -> 'adarsh'. Only call after is_const_ref() returns True."""
    return _ref_kind(source_ref)[1]


def is_map_ref(source_ref) -> bool:
    """True if source_ref is a 'map:v1||v2||...' positional mapping."""
    return _ref_kind(source_ref)[0] == "map"


def map_values(source_ref) -> list:
    """'map:A||B||C' -> ['A', 'B', 'C']. Only call after is_map_ref()."""
    payload = _ref_kind(source_ref)[1]
    return [v.strip() for v in payload.split("||")]


# ---- fn:<name> — computed values evaluated at load time ---------------------
# Each entry: name -> (callable(context), compatible data_types).
# context is a dict with optional keys: file_name, sequence (counter).
# Simple functions ignore the context; file_name/sequence use it.

import re
import uuid as _uuid
from datetime import date, datetime

_sequence_counters = {}  # table_name -> next value


def _fn_now(ctx):
    return datetime.now()


def _fn_today(ctx):
    return date.today()


def _fn_uuid(ctx):
    return str(_uuid.uuid4())


def _fn_file_name(ctx):
    return ctx.get("file_name", "")


def _fn_sequence(ctx):
    key = ctx.get("_seq_key", "_default")
    _sequence_counters[key] = _sequence_counters.get(key, 0) + 1
    return _sequence_counters[key]


def fn_reset_sequence(table_name: str = None) -> None:
    """Reset sequence counters. Call before a new load."""
    if table_name:
        _sequence_counters.pop(table_name, None)
    else:
        _sequence_counters.clear()


FN_REGISTRY = {
    "now":       (_fn_now,       {"timestamp", "text"}),
    "today":     (_fn_today,     {"date", "text"}),
    "uuid":      (_fn_uuid,      {"text"}),
    "file_name": (_fn_file_name, {"text"}),
    "sequence":  (_fn_sequence,  {"integer", "numeric", "text"}),
}


def is_fn_ref(source_ref) -> bool:
    """True if source_ref is a 'fn:<name>' computed reference."""
    return _ref_kind(source_ref)[0] == "fn"


def fn_name(source_ref) -> str:
    """'fn:now' -> 'now'. Only call after is_fn_ref() returns True."""
    return _ref_kind(source_ref)[1]


def fn_evaluate(source_ref, context=None):
    """Call the registered function and return its value."""
    name = fn_name(source_ref)
    func, _ = FN_REGISTRY[name]
    return func(context or {})


# ---- expr:<expression> — computed from other columns -----------------------
# Tokens: {A} = column ref, const:value, fn:name, "literal", number
# Operators: + - * / (numeric), & (string concatenation)
# Parentheses: ( ) for grouping
# Unary minus: -{A}, -(expr)

_EXPR_TOKEN = re.compile(
    r'\{([A-Za-z_][A-Za-z0-9_]*)\}'  # {A}, {AM} (col letter) or {column_name} (name ref)
    r'|fn:(\w+)'             # fn:now, fn:today
    r'|const:([^&+\-*/\s()]+)'  # const:adarsh, const:100
    r'|"([^"]*)"'            # "literal string"
    r"|'([^']*)'"             # 'literal string'
    r'|(\d+(?:\.\d+)?)'      # numeric literal
    r'|([&+\-*/()])'         # operator or parenthesis
)

# Cache: expression body -> parsed tokens
_expr_cache = {}


def is_expr_ref(source_ref) -> bool:
    """True if source_ref is an 'expr:...' expression."""
    return _ref_kind(source_ref)[0] == "expr"


def expr_body(source_ref) -> str:
    """'expr:{A} + {B}' -> '{A} + {B}'."""
    return _ref_kind(source_ref)[1]


def parse_expr(body: str) -> list:
    """Tokenize an expression body into a list of (type, value) pairs.

    Types: 'col', 'fn', 'const', 'literal', 'number', 'op', 'lparen', 'rparen'.
    Raises ValueError on unparseable content. Results are cached.
    """
    if body in _expr_cache:
        return _expr_cache[body]
    tokens = []
    pos = 0
    text = body.strip()
    while pos < len(text):
        if text[pos].isspace():
            pos += 1
            continue
        m = _EXPR_TOKEN.match(text, pos)
        if not m:
            raise ValueError(f"unexpected character at position {pos}: {text[pos:]!r}")
        if m.group(1) is not None:
            ref = m.group(1)
            # All uppercase letters = Excel column (A, AM); otherwise = column name
            if ref.isalpha() and ref.isupper():
                tokens.append(("col", ref))
            else:
                tokens.append(("ref", ref))  # column name reference
        elif m.group(2) is not None:
            tokens.append(("fn", m.group(2)))
        elif m.group(3) is not None:
            tokens.append(("const", m.group(3)))
        elif m.group(4) is not None:
            tokens.append(("literal", m.group(4)))
        elif m.group(5) is not None:
            tokens.append(("literal", m.group(5)))
        elif m.group(6) is not None:
            tokens.append(("number", float(m.group(6))))
        elif m.group(7) is not None:
            ch = m.group(7)
            if ch == "(":
                tokens.append(("lparen", "("))
            elif ch == ")":
                tokens.append(("rparen", ")"))
            else:
                tokens.append(("op", ch))
        pos = m.end()
    _expr_cache[body] = tokens
    return tokens


def validate_expr(body: str) -> list:
    """Parse and validate an expression. Returns a list of error strings (empty = OK)."""
    errors = []
    try:
        tokens = parse_expr(body)
    except ValueError as exc:
        return [str(exc)]
    if not tokens:
        return ["expression is empty"]
    for kind, value in tokens:
        if kind == "fn" and value not in FN_REGISTRY:
            errors.append(f"unknown function 'fn:{value}' in expression. "
                          f"Available: {', '.join(sorted(FN_REGISTRY))}")
    # Check balanced parentheses
    depth = 0
    for kind, value in tokens:
        if kind == "lparen":
            depth += 1
        elif kind == "rparen":
            depth -= 1
            if depth < 0:
                errors.append("unmatched closing parenthesis ')'")
                break
    if depth > 0:
        errors.append(f"unmatched opening parenthesis — {depth} unclosed '('")
    return errors


def expr_column_refs(body: str) -> list:
    """Return the column letters referenced by an expression, e.g. ['A', 'B']."""
    try:
        tokens = parse_expr(body)
    except ValueError:
        return []
    return [value for kind, value in tokens if kind in ("col", "ref")]


def evaluate_expr(body: str, cell_reader, context=None) -> object:
    """Evaluate an expression given a cell_reader(letter) -> raw value function.

    Uses recursive descent to handle parentheses and operator precedence.
    NULL propagation: arithmetic with NULL -> NULL (like SQL).
    Returns the computed value (number, string, or None).
    """
    tokens = parse_expr(body)
    ctx = context or {}
    pos = [0]  # mutable index for recursive descent

    def _resolve():
        """Resolve the next operand (handles unary minus and parentheses)."""
        if pos[0] >= len(tokens):
            raise ValueError("unexpected end of expression")
        kind, value = tokens[pos[0]]
        # Unary minus
        if kind == "op" and value == "-":
            pos[0] += 1
            operand = _resolve()
            if operand is None:
                return None
            n = _to_num(operand)
            if n is None:
                raise ValueError(f"unary minus on non-numeric value: -{operand!r}")
            return -n
        # Parenthesized sub-expression
        if kind == "lparen":
            pos[0] += 1
            result = _parse_concat()
            if pos[0] < len(tokens) and tokens[pos[0]][0] == "rparen":
                pos[0] += 1
            return result
        # Operands
        pos[0] += 1
        if kind in ("col", "ref"):
            return cell_reader(value)
        if kind == "fn":
            func, _ = FN_REGISTRY[value]
            return func(ctx)
        if kind in ("const", "literal"):
            return value
        if kind == "number":
            return value
        raise ValueError(f"unexpected token: {kind} {value!r}")

    def _parse_muldiv():
        """Parse * and / (highest precedence among binary ops)."""
        left = _resolve()
        while pos[0] < len(tokens) and tokens[pos[0]] == ("op", "*") or \
              pos[0] < len(tokens) and tokens[pos[0]] == ("op", "/"):
            op = tokens[pos[0]][1]
            pos[0] += 1
            right = _resolve()
            left = _apply_op(left, op, right)
        return left

    def _parse_addsub():
        """Parse + and - (medium precedence)."""
        left = _parse_muldiv()
        while pos[0] < len(tokens) and tokens[pos[0]] == ("op", "+") or \
              pos[0] < len(tokens) and tokens[pos[0]] == ("op", "-"):
            op = tokens[pos[0]][1]
            pos[0] += 1
            right = _parse_muldiv()
            left = _apply_op(left, op, right)
        return left

    def _parse_concat():
        """Parse & (lowest precedence)."""
        left = _parse_addsub()
        while pos[0] < len(tokens) and tokens[pos[0]] == ("op", "&"):
            pos[0] += 1
            right = _parse_addsub()
            left = _apply_op(left, "&", right)
        return left

    def _apply_op(left, op, right):
        if op == "&":
            ls = str(left) if left is not None else ""
            rs = str(right) if right is not None else ""
            return ls + rs
        # NULL propagation: arithmetic with NULL -> NULL
        ln = _to_num(left)
        rn = _to_num(right)
        if ln is None or rn is None:
            return None
        if op == "+":
            return ln + rn
        if op == "-":
            return ln - rn
        if op == "*":
            return ln * rn
        if op == "/":
            if rn == 0:
                return None
            return ln / rn
        raise ValueError(f"unknown operator: {op!r}")

    def _to_num(value):
        if isinstance(value, (int, float)):
            return value
        if value is None:
            return None
        try:
            return float(str(value))
        except (ValueError, TypeError):
            return None

    result = _parse_concat()
    return result


# ---- row_filter — row-level filtering in sheet_config ----------------------
# Syntax: col:LETTER op value [AND/OR col:LETTER op value ...]
# Operators: =, !=, >, <, >=, <=, contains, not_contains, is_empty, is_not_empty
# Value: "text" or number. Comparisons are case-insensitive for text.

_WHERE_CONDITION = re.compile(
    r'col:([A-Z]+)'             # col:A, col:AM — same as source_ref
    r'\s*(=|!=|>=|<=|>|<|contains|not_contains|is_empty|is_not_empty)'  # operator
    r'(?:\s+"([^"]*)"'          # "text value"
    r"|\\s+'([^']*)'"           # 'text value'
    r'|\s+(\d+(?:\.\d+)?))?'   # numeric value (optional for is_empty/is_not_empty)
)


def parse_where(where_str: str) -> list:
    """Parse a where clause into a list of (col_letter, op, value, combiner) tuples.

    combiner is 'AND' or 'OR' (default AND between conditions).
    Returns [] for empty/None input.
    """
    text = str(where_str or "").strip()
    if not text:
        return []
    conditions = []
    # Split on AND/OR (case insensitive)
    parts = re.split(r'\s+(AND|OR)\s+', text, flags=re.IGNORECASE)
    combiners = []
    filter_parts = []
    for i, part in enumerate(parts):
        if part.upper() in ("AND", "OR"):
            combiners.append(part.upper())
        else:
            filter_parts.append(part.strip())
    # Default combiner is AND
    for i, part in enumerate(filter_parts):
        m = _WHERE_CONDITION.match(part)
        if not m:
            raise ValueError(f"cannot parse where condition: {part!r}")
        col_letter = m.group(1)
        op = m.group(2)
        if m.group(3) is not None:
            value = m.group(3)
        elif m.group(4) is not None:
            value = m.group(4)
        elif m.group(5) is not None:
            value = float(m.group(5))
        else:
            value = None  # for is_empty / is_not_empty
        combiner = combiners[i - 1] if i > 0 and i - 1 < len(combiners) else "AND"
        conditions.append((col_letter, op, value, combiner))
    return conditions


def validate_where(where_str: str) -> list:
    """Validate a where clause. Returns list of error strings (empty = OK)."""
    try:
        conditions = parse_where(where_str)
    except ValueError as exc:
        return [str(exc)]
    errors = []
    for col_letter, op, value, _ in conditions:
        if op in ("is_empty", "is_not_empty") and value is not None:
            errors.append(f"{op} does not take a value")
        if op not in ("is_empty", "is_not_empty") and value is None:
            errors.append(f"{op} requires a value (e.g. {{A}} {op} \"text\" or {{A}} {op} 123)")
    return errors


def evaluate_where(conditions: list, cell_reader) -> bool:
    """Evaluate parsed where conditions. cell_reader(letter) -> raw cell value.

    Returns True if the row should be loaded, False to skip.
    """
    if not conditions:
        return True
    results = []
    combiners = []
    for col_letter, op, value, combiner in conditions:
        raw = cell_reader(col_letter)
        result = _eval_condition(raw, op, value)
        results.append(result)
        combiners.append(combiner)
    # Evaluate: AND has higher precedence than OR
    # Group by OR, then AND within each group
    final = results[0]
    for i in range(1, len(results)):
        if combiners[i] == "OR":
            final = final or results[i]
        else:  # AND
            final = final and results[i]
    return final


def _eval_condition(raw, op, value) -> bool:
    """Evaluate a single condition."""
    if op == "is_empty":
        return raw is None or str(raw).strip() == ""
    if op == "is_not_empty":
        return raw is not None and str(raw).strip() != ""
    raw_str = str(raw).strip().lower() if raw is not None else ""
    val_str = str(value).strip().lower() if value is not None else ""
    if op == "contains":
        return val_str in raw_str
    if op == "not_contains":
        return val_str not in raw_str
    if op == "=":
        # Try numeric comparison first
        rn = _try_num(raw)
        vn = _try_num(value)
        if rn is not None and vn is not None:
            return rn == vn
        return raw_str == val_str
    if op == "!=":
        rn = _try_num(raw)
        vn = _try_num(value)
        if rn is not None and vn is not None:
            return rn != vn
        return raw_str != val_str
    # Numeric comparisons: >, <, >=, <=
    rn = _try_num(raw)
    vn = _try_num(value)
    if rn is None or vn is None:
        return False  # can't compare non-numeric
    if op == ">":
        return rn > vn
    if op == "<":
        return rn < vn
    if op == ">=":
        return rn >= vn
    if op == "<=":
        return rn <= vn
    return False


def _try_num(value):
    """Try to convert to float, return None on failure."""
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        return None
    try:
        return float(str(value))
    except (ValueError, TypeError):
        return None


def where_column_refs(where_str: str) -> list:
    """Return column letters referenced in a where clause."""
    try:
        conditions = parse_where(where_str)
    except ValueError:
        return []
    return [col for col, _, _, _ in conditions]


def column_letter(source_ref) -> str:
    """'col:AM' -> 'AM'. Raises ValueError on any other shape."""
    text = str(source_ref or "").strip()
    kind, _, letter = text.partition(":")
    letter = letter.strip().upper()
    if kind.strip().lower() != "col" or not letter.isalpha():
        raise ValueError(f"{text!r} is not a valid source_ref "
                         f"(use col:<letter>, const:<value>, fn:<name>, "
                         f"expr:<expression>, or map:v1||v2||...)")
    return letter


# ------------------------------------------------------------- validation


def _check_target(settings, resolved, issues) -> None:
    where = "target_config"
    if not settings:
        issues.append(Issue("warning", where, "no target_config sheet - defaulting to "
                                              "sqlite with no table prefix; add the sheet to "
                                              "pin the database and schema to this "
                                              "configuration"))
    for key in settings:
        if key not in TARGET_SETTINGS:
            issues.append(Issue("error", f"{where}[{key}]",
                                f"unknown setting - use one of {TARGET_SETTINGS}"))
        if key in ("pghost", "pguser", "pgpassword", "password", "host", "user"):
            issues.append(Issue("error", f"{where}[{key}]",
                                "credentials must never live in the workbook - keep them in .env"))

    if resolved.target not in ("sqlite", "postgres"):
        issues.append(Issue("error", f"{where}[target]",
                            f"{resolved.target!r} is not 'sqlite' or 'postgres'"))
    if not resolved.database:
        issues.append(Issue("warning", f"{where}[database]",
                            "not set - the SQLite file path / PostgreSQL database name "
                            "must then come from the command line or PGDATABASE"))
    elif resolved.target == "postgres" and not IDENTIFIER.match(resolved.database):
        issues.append(Issue("error", f"{where}[database]",
                            f"{resolved.database!r} is not a plain database name"))
    if resolved.id_type not in ID_TYPES:
        issues.append(Issue("error", f"{where}[id_type]",
                            f"{resolved.id_type!r} is not one of {ID_TYPES}"))
    if resolved.db_schema:
        if resolved.target == "sqlite":
            issues.append(Issue("warning", f"{where}[db_schema]",
                                "SQLite has no schemas - the setting is ignored"))
        elif not IDENTIFIER.match(resolved.db_schema):
            issues.append(Issue("error", f"{where}[db_schema]",
                                f"{resolved.db_schema!r} is not a plain schema name"))


def _check_config(sheets, columns, prefix, issues) -> None:
    if not IDENTIFIER.match(f"{prefix}x"):
        issues.append(Issue("error", "table_prefix", f"{prefix!r} is not a usable name prefix"))

    seen_tables = set()
    for sheet in sheets:
        table = str(sheet["table_name"]).strip()
        where = f"sheet_config[{table}]"

        if not IDENTIFIER.match(table) or len(f"{prefix}{table}") > 63:
            issues.append(Issue("error", where, "table_name must be letters/digits/underscores, "
                                                "start with a letter, and stay under 63 characters "
                                                "including the prefix"))
        if table in seen_tables:
            issues.append(Issue("error", where, "table_name is used twice - one row, one table"))
        seen_tables.add(table)

        if not str(sheet.get("sheet_name") or "").strip():
            issues.append(Issue("error", where, "sheet_name is empty"))

        layout = str(sheet.get("layout") or "table").strip().lower()
        if layout not in LAYOUTS:
            issues.append(Issue("error", where, f"layout {layout!r} is not one of {LAYOUTS}"))

        start = _positive_int(sheet.get("data_start_row"), where, "data_start_row", issues, True)
        end = _positive_int(sheet.get("data_end_row"), where, "data_end_row", issues, False)
        header = _positive_int(sheet.get("header_row"), where, "header_row", issues, False)
        if start and end and end < start:
            issues.append(Issue("error", where, f"data_end_row {end} is before data_start_row {start}"))
        if start and header and header >= start:
            issues.append(Issue("warning", where, f"header_row {header} is inside the data range "
                                                  f"- row {start} onwards is read as data"))
        if not end:
            issues.append(Issue("warning", where, "No end row set — reads to the last row. "
                                                  "Set data_end_row if the sheet has totals or notes below the data."))

        where_clause = str(sheet.get("row_filter") or "").strip()
        if where_clause:
            errs = validate_where(where_clause)
            for err in errs:
                issues.append(Issue("error", where, f"row_filter: {err}"))

        cols = columns.get(sheet["table_name"], [])
        if not cols:
            issues.append(Issue("error", where, "no column_config rows for this table"))

        seen_names, seen_refs = set(), {}
        for col in cols:
            name = str(col["column_name"]).strip()
            cwhere = f"column_config[{table}.{name}]"

            if not IDENTIFIER.match(name) or len(name) > 63:
                issues.append(Issue("error", cwhere, "column_name must be letters/digits/underscores, "
                                                     "start with a letter, max 63 characters"))
            if name in LINEAGE or name == f"{table}_id":
                issues.append(Issue("error", cwhere, f"{name} is a reserved lineage column - rename it"))
            if name in seen_names:
                issues.append(Issue("error", cwhere, "column_name is used twice in this table"))
            seen_names.add(name)

            dtype = str(col.get("data_type") or "text").strip().lower()
            if dtype not in VALUE_TYPES:
                issues.append(Issue("error", cwhere, f"data_type {dtype!r} is not one of {VALUE_TYPES}"))

            script_spec = str(col.get("script") or "").strip()
            if script_spec:
                unknown = validate_script(script_spec)
                if unknown:
                    issues.append(Issue("error", cwhere,
                                        f"unknown script(s): {', '.join(unknown)}. "
                                        f"Available: {', '.join(sorted(scripts.SCRIPTS))}"))

            for field, allowed in (("nullable", "YN"), ("is_key", "YN")):
                flag = str(col.get(field) or ("Y" if field == "nullable" else "N")).strip().upper()
                if flag not in allowed:
                    issues.append(Issue("error", cwhere, f"{field} must be Y or N, not {flag!r}"))

            if is_map_ref(col.get("source_ref")):
                vals = map_values(col.get("source_ref"))
                if not vals or vals == [""]:
                    issues.append(Issue("error", cwhere, "map: needs at least one value "
                                                         "(e.g. map:Label1||Label2)"))
            elif is_const_ref(col.get("source_ref")):
                cv = const_value(col.get("source_ref"))
                if not cv:
                    issues.append(Issue("error", cwhere, "const: value is empty"))
            elif is_fn_ref(col.get("source_ref")):
                fname = fn_name(col.get("source_ref"))
                if fname not in FN_REGISTRY:
                    issues.append(Issue("error", cwhere,
                                        f"unknown function 'fn:{fname}'. "
                                        f"Available: {', '.join(sorted(FN_REGISTRY))}"))
                else:
                    _, compatible = FN_REGISTRY[fname]
                    if dtype not in compatible:
                        issues.append(Issue("error", cwhere,
                                            f"fn:{fname} produces a value compatible with "
                                            f"{', '.join(sorted(compatible))}, not {dtype!r}"))
            elif is_expr_ref(col.get("source_ref")):
                body = expr_body(col.get("source_ref"))
                errs = validate_expr(body)
                for err in errs:
                    issues.append(Issue("error", cwhere, f"expr: {err}"))
                for letter in expr_column_refs(body):
                    if letter in seen_refs:
                        pass  # OK — expressions *should* reference other columns
                    seen_refs.setdefault(letter, name)
            else:
                try:
                    letter = column_letter(col.get("source_ref"))
                except ValueError as exc:
                    issues.append(Issue("error", cwhere, str(exc)))
                    continue
                if letter in seen_refs:
                    issues.append(Issue("warning", cwhere, f"col:{letter} is already mapped to "
                                                           f"{seen_refs[letter]} - the cell is stored twice"))
                seen_refs.setdefault(letter, name)

            if col.get("column_order") in (None, ""):
                issues.append(Issue("warning", cwhere, "column_order is empty - ordering falls back to 0"))

            ref = str(col.get("references") or "").strip()
            if ref:
                if "." not in ref:
                    issues.append(Issue("error", cwhere,
                                        f"references must be table_name.column_name, not {ref!r}"))
                else:
                    ref_table, ref_col = ref.rsplit(".", 1)
                    if ref_table not in {str(s["table_name"]).strip() for s in sheets}:
                        issues.append(Issue("warning", cwhere,
                                            f"references {ref_table!r} which is not an active table"))

            nd = str(col.get("null_default") or "").strip().lower()
            if nd and nd != "null":
                if dtype in ("numeric", "integer") and nd not in ("0", "0.0"):
                    try:
                        float(nd)
                    except ValueError:
                        issues.append(Issue("error", cwhere,
                                            f"null_default {nd!r} is not a valid number"))
                if dtype == "boolean" and nd not in ("0", "1", "true", "false"):
                    issues.append(Issue("error", cwhere,
                                        f"null_default {nd!r} is not a valid boolean (0/1/true/false)"))

            dfmt = str(col.get("date_format") or "").strip()
            if dfmt:
                if dtype not in ("date", "timestamp"):
                    issues.append(Issue("warning", cwhere,
                                        f"date_format is set but data_type is {dtype!r}, "
                                        f"not date or timestamp — it will be ignored"))
                else:
                    # Validate the format string with a test date
                    import datetime as _dt
                    try:
                        _dt.datetime.strptime("01/01/2026", dfmt)
                    except ValueError:
                        try:
                            _dt.datetime.strptime("2026-01-01", dfmt)
                        except ValueError:
                            issues.append(Issue("warning", cwhere,
                                                f"date_format {dfmt!r} may not match common dates "
                                                f"— verify it parses your source values correctly"))

    for table in columns:
        if str(table).strip() not in seen_tables:
            issues.append(Issue("warning", f"column_config[{table}]",
                                "no active sheet_config row - these columns are ignored"))


def _positive_int(value, where, field, issues, required):
    if value in (None, ""):
        if required:
            issues.append(Issue("error", where, f"{field} is required"))
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        issues.append(Issue("error", where, f"{field} must be a whole number, not {value!r}"))
        return None
    if number < 1:
        issues.append(Issue("error", where, f"{field} must be 1 or more, not {number}"))
        return None
    return number


def _check_source(sheets, columns, source: Path, issues, source_name: str = None) -> None:
    """Dry run of the load: every configured cell is read and cast, nothing is written."""
    fn_reset_sequence()  # clean slate for validation
    import csv_adapter
    wb = csv_adapter.open_source(source, source_name)
    for sheet in sheets:
        table, name = str(sheet["table_name"]).strip(), str(sheet.get("sheet_name") or "").strip()
        where = f"{source.name}[{name}]"
        if name not in wb.sheetnames:
            issues.append(Issue("error", where, f"Sheet \"{name}\" not found in the source file. "
                                                f"Available sheets: {', '.join(wb.sheetnames)}"))
            continue
        ws = wb[name]
        try:
            start = int(sheet["data_start_row"])
        except (TypeError, ValueError, KeyError):
            continue                                    # already reported by _check_config
        end = int(sheet["data_end_row"]) if sheet.get("data_end_row") else ws.max_row
        if start > ws.max_row:
            issues.append(Issue("warning", where, f"Start row {start} is past the last row in the sheet "
                                                  f"(row {ws.max_row}) — this table will be empty"))
            continue

        # kind: 'static' (const/fn), 'col', 'expr', or 'map'
        cols = []        # (col_config, kind, letter_or_None, index_or_None, static_or_body)
        for col in columns.get(sheet["table_name"], []):
            if is_map_ref(col.get("source_ref")):
                vals = map_values(col.get("source_ref"))
                row_count = end - start + 1
                if len(vals) != row_count:
                    issues.append(Issue("warning", f"{where}[{col['column_name']}]",
                                        f"map: has {len(vals)} value(s) but the block has "
                                        f"{row_count} row(s) ({start}-{end}). Extra values "
                                        f"are ignored; missing positions get NULL."))
                cols.append((col, "map", None, None, vals))
                continue
            if is_const_ref(col.get("source_ref")):
                cv = const_value(col.get("source_ref"))
                cols.append((col, "static", None, None, cv))
                continue
            if is_fn_ref(col.get("source_ref")):
                _ctx = {"file_name": source.name, "_seq_key": f"_validate_{table}"}
                cols.append((col, "static", None, None, fn_evaluate(col.get("source_ref"), _ctx)))
                continue
            if is_expr_ref(col.get("source_ref")):
                body = expr_body(col.get("source_ref"))
                # Check that referenced Excel columns are within range
                # (column name refs are resolved at eval time, not here)
                try:
                    tokens = parse_expr(body)
                except ValueError:
                    tokens = []
                for kind, ref_letter in tokens:
                    if kind == "col":  # Excel column letter only
                        ref_idx = column_index_from_string(ref_letter)
                        if ref_idx > ws.max_column:
                            issues.append(Issue("error", f"{where}!{ref_letter}",
                                                f"Column {ref_letter} (referenced in expr for "
                                                f"\"{col['column_name']}\") is beyond the data"))
                cols.append((col, "expr", None, None, body))
                continue
            try:
                letter = column_letter(col.get("source_ref"))
            except ValueError:
                continue
            index = column_index_from_string(letter)
            if index > ws.max_column:
                issues.append(Issue("error", f"{where}!{letter}",
                                    f"Column {letter} (\"{col['column_name']}\") is beyond the "
                                    f"data in the sheet — the source file may have fewer columns than expected"))
                continue
            cols.append((col, "col", letter, index, None))

        # Parse where filter
        where_clause = str(sheet.get("row_filter") or "").strip()
        where_conditions = parse_where(where_clause) if where_clause else []
        filtered = 0

        rows = skipped = 0
        for row_num in range(start, min(end, ws.max_row) + 1):
            # Apply where filter
            if where_conditions:
                def _where_reader(ltr, _ws=ws, _row=row_num):
                    return _ws.cell(_row, column_index_from_string(ltr)).value
                if not evaluate_where(where_conditions, _where_reader):
                    filtered += 1
                    continue
            values, bad = [], []
            computed_vals = {}
            for col, ckind, letter, index, extra in cols:
                col_name = str(col.get("column_name", "")).strip()
                dfmt = str(col.get("date_format") or "").strip() or None
                if ckind == "map":
                    idx = row_num - start
                    raw = extra[idx] if idx < len(extra) else None
                    try:
                        v = cast(raw, str(col.get("data_type") or "text").strip().lower(), date_format=dfmt)
                        values.append(v)
                        computed_vals[col_name] = v
                    except ValueError as exc:
                        values.append(None)
                        bad.append((col, f"map[{idx}]", exc))
                    continue
                if ckind == "static":
                    try:
                        v = cast(extra, str(col.get("data_type") or "text").strip().lower(), date_format=dfmt)
                        values.append(v)
                        computed_vals[col_name] = v
                    except ValueError as exc:
                        values.append(None)
                        bad.append((col, f"const:{extra}", exc))
                    continue
                if ckind == "expr":
                    def _reader(ref, _ws=ws, _row=row_num, _computed=computed_vals):
                        if ref in _computed:
                            return _computed[ref]
                        return _ws.cell(_row, column_index_from_string(ref)).value
                    _ctx = {"file_name": source.name, "_seq_key": f"_validate_{table}"}
                    try:
                        raw = evaluate_expr(extra, _reader, _ctx)
                        v = cast(raw, str(col.get("data_type") or "text").strip().lower(), date_format=dfmt)
                        values.append(v)
                        computed_vals[col_name] = v
                    except ValueError as exc:
                        values.append(None)
                        bad.append((col, "expr", exc))
                    continue
                raw = ws.cell(row_num, index).value
                try:
                    v = cast(raw, str(col.get("data_type") or "text").strip().lower(), date_format=dfmt)
                    values.append(v)
                    computed_vals[col_name] = v
                except ValueError as exc:
                    values.append(None)
                    bad.append((col, letter, exc))
            if all(v is None for v in values):
                continue
            for col, letter, exc in bad:
                severity = "warning" if _nullable(col) else "error"
                issues.append(Issue(severity, f"{where}!{letter}{row_num}",
                                    f"Column \"{col['column_name']}\" — value doesn't match "
                                    f"type \"{col.get('data_type')}\" ({exc}). "
                                    + ("Stored as empty." if severity == "warning"
                                       else "This column is required, so the row is skipped.")))
            required = [col["column_name"] for (col, *_), value in zip(cols, values)
                        if value is None and not _nullable(col)]
            if required:
                skipped += 1
                issues.append(Issue("warning", f"{where}!{row_num}",
                                    f"Row {row_num} skipped — required column(s) are empty: {', '.join(required)}"))
                continue
            rows += 1
        if not rows:
            issues.append(Issue("warning", where, f"Empty section — 0 rows found in \"{name}\" rows {start}-{end}"
                                                  + (f" ({skipped} skipped due to missing data)" if skipped else "")))


def _nullable(col) -> bool:
    return str(col.get("nullable") or "Y").strip().upper() != "N"


def validate(config: Path, source: Path = None, prefix: str = None, target: str = None,
             database: str = None, id_type: str = None, source_name: str = None) -> list:
    """Check the configuration, and optionally one source workbook against it.

    Returns a list of Issue(severity, where, message); an empty list, or a list
    of warnings only, means executor.py can push this pair.

    *source_name* overrides the CSV sheet name when the on-disk filename is a
    content-addressed hash (e.g. uploaded files). Pass the original filename
    stem so that `sheet_config.sheet_name` can match.
    """
    issues = []
    resolved = resolve_target(config, target, database, prefix, id_type)
    _check_target(read_target(config), resolved, issues)
    sheets, columns = read_config(config)
    if not sheets:
        issues.append(Issue("error", "sheet_config", "no active rows - nothing would be created"))
    _check_config(sheets, columns, resolved.prefix, issues)
    if source and not [i for i in issues if i.severity == "error"]:
        _check_source(sheets, columns, source, issues, source_name)
    return issues


# ---------------------------------------------------------------- the DDL


def render_ddl(sheets, columns, dialect: str, prefix: str, id_type: str = "integer") -> str:
    """The configuration as CREATE TABLE statements - one per active table."""
    t = ddl_types(dialect, id_type)
    out = ["-- Generated by validator.py from the configuration workbook.",
           f"-- dialect: {dialect}, id_type: {id_type}. Do not edit by hand; "
           "change the config and regenerate.",
           "", CONTROL_DDL.format(p=prefix, **t)]

    for sheet in sheets:
        table = f"{prefix}{str(sheet['table_name']).strip()}"
        cols = columns.get(sheet["table_name"], [])
        lines = [f"    {str(sheet['table_name']).strip()}_id {t['id']},",
                 f"    file_id {t['text']} NOT NULL,",
                 f"    file_name {t['text']} NOT NULL,",
                 f"    file_sha256 {t['text']} NOT NULL,",
                 f"    source_ref {t['text']},",
                 f"    sheet_name {t['text']} NOT NULL,",
                 f"    source_row_num {t['integer']} NOT NULL,"]
        keys = []
        for col in cols:
            name = str(col["column_name"]).strip()
            dtype = str(col.get("data_type") or "text").strip().lower()
            null = "" if _nullable(col) else " NOT NULL"
            lines.append(f"    {name} {t[dtype]}{null},")
            if str(col.get("is_key") or "N").strip().upper() == "Y":
                keys.append(name)

        note = sheet.get("notes") or ""
        out.append(f"-- {sheet['sheet_name']}!row {sheet.get('data_start_row')}+"
                   + (f" - {note}" if note else ""))
        out.append(f"CREATE TABLE {table} (")
        out.append("\n".join(lines).rstrip(","))
        out.append(");")
        out.append(f"CREATE UNIQUE INDEX ux_{table}_row ON {table} (file_id, sheet_name, source_row_num);")
        out.append(f"CREATE INDEX ix_{table}_file ON {table} (file_id);")
        if keys:
            out.append(f"CREATE INDEX ix_{table}_key ON {table} ({', '.join(keys)});")

        # Metadata comments (PostgreSQL only)
        if dialect == "postgres":
            desc = str(sheet.get("description") or "").strip()
            domain = str(sheet.get("domain") or "").strip()
            table_comment = desc
            if domain:
                table_comment = f"[{domain}] {table_comment}" if table_comment else f"[{domain}]"
            if table_comment:
                escaped = table_comment.replace("'", "''")
                out.append(f"COMMENT ON TABLE {table} IS '{escaped}';")
            for col in cols:
                col_desc = str(col.get("description") or "").strip()
                col_unit = str(col.get("unit") or "").strip()
                col_comment = col_desc
                if col_unit:
                    col_comment = f"{col_comment} ({col_unit})" if col_comment else col_unit
                if col_comment:
                    cname = str(col["column_name"]).strip()
                    escaped = col_comment.replace("'", "''")
                    out.append(f"COMMENT ON COLUMN {table}.{cname} IS '{escaped}';")

        out.append("")
    return "\n".join(out) + "\n"


def write_ddl(config: Path, output: Path, dialect: str, prefix: str = "",
              id_type: str = "integer") -> int:
    """Render the DDL for a configuration that has already been validated."""
    sheets, columns = read_config(config)
    output.write_text(render_ddl(sheets, columns, dialect, prefix, id_type))
    return len(sheets)


# ----------------------------------------------------------------- the CLI


def main() -> None:
    ap = argparse.ArgumentParser(description="validate the configuration workbook, and the "
                                             "source workbook against it")
    ap.add_argument("config", help="configuration workbook (sheet_config + column_config)")
    ap.add_argument("source", nargs="?", help="source workbook to check against the configuration")
    ap.add_argument("--target", choices=("sqlite", "postgres"), default=None,
                    help="override target_config[target]")
    ap.add_argument("--database", default=None, help="override target_config[database]")
    ap.add_argument("--prefix", default=None, help="override target_config[table_prefix]")
    ap.add_argument("--id-type", choices=ID_TYPES, default=None,
                    help="override target_config[id_type] - integer keys or UUID keys")
    ap.add_argument("--ddl", metavar="FILE", help="write the CREATE TABLE statements here if valid")
    ap.add_argument("--dialect", choices=sorted(DDL_TYPES), default=None,
                    help="DDL flavour (default: the configured target)")
    ap.add_argument("--max-issues", type=int, default=40, metavar="N",
                    help="stop printing after N issues of each severity (default 40)")
    args = ap.parse_args()

    config = Path(args.config)
    resolved = resolve_target(config, args.target, args.database, args.prefix, args.id_type)
    issues = validate(config, Path(args.source) if args.source else None,
                      args.prefix, args.target, args.database, args.id_type)
    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity == "warning"]

    for label, found in (("ERROR", errors), ("warning", warnings)):
        for issue in found[:args.max_issues]:
            print(f"{label:<8} {issue.where}: {issue.message}")
        if len(found) > args.max_issues:
            print(f"{label:<8} ... and {len(found) - args.max_issues} more")

    checked = Path(args.config).name + (f" + {Path(args.source).name}" if args.source else "")
    if errors:
        print(f"\n{checked}: NOT loadable - {len(errors)} error(s), {len(warnings)} warning(s)")
        raise SystemExit(1)

    dialect = args.dialect or resolved.target
    print(f"target: {resolved.target}"
          + (f" {resolved.database}" if resolved.database else "")
          + (f" (schema {resolved.db_schema})" if resolved.db_schema else "")
          + f", table prefix {resolved.prefix or '(none)'}"
          + f", {resolved.id_type} keys")
    if args.ddl:
        tables = write_ddl(config, Path(args.ddl), dialect, resolved.prefix, resolved.id_type)
        print(f"wrote {args.ddl}: {tables} tables + 2 control tables "
              f"({dialect}, {resolved.id_type} keys)")
    print(f"{checked}: OK to load - 0 errors, {len(warnings)} warning(s)")


if __name__ == "__main__":
    main()
