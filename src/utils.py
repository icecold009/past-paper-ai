from __future__ import annotations

import re
from typing import Any


_FILENAME_RE = re.compile(
    r"^(?P<subject>\d{4})_(?P<paper>p[12])_(?P<year>\d{4})_(?P<session_code>mj|on|fm)_(?P<variant>\d{2})_(?P<doc_type>qp|ms)\.pdf$",
    re.IGNORECASE,
)

_SESSION_MAP = {
    "mj": "May/June",
    "on": "Oct/Nov",
    "fm": "Feb/March",
}


def parse_9618_filename(filename: str) -> dict[str, Any] | None:
    """Parse a normalized CAIE 9618 PDF filename.

    Expected format:
        9618_p1_2023_mj_11_qp.pdf
    """

    match = _FILENAME_RE.match(filename.strip())
    if not match:
        return None

    groups = match.groupdict()
    session_code = groups["session_code"].lower()
    return {
        "subject": groups["subject"],
        "paper": groups["paper"].lower(),
        "year": int(groups["year"]),
        "session_code": session_code,
        "session": _SESSION_MAP.get(session_code),
        "variant": groups["variant"],
        "doc_type": groups["doc_type"].lower(),
    }
