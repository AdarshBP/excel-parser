"""The bridge to the parser: the app calls the same functions the CLI does.

`tools/` is imported as-is - no parsing, casting or DDL logic is reimplemented
here, so a fix in the parser is a fix in the app.
"""
import sys

import state

TOOLS = state.PROJECT_ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import db as dbmod          # noqa: E402
import executor             # noqa: E402
import preview              # noqa: E402
import validator            # noqa: E402

__all__ = ["dbmod", "executor", "preview", "validator"]
