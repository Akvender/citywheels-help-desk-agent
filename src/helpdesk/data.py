"""Loading CityWheels data. Kept separate from the tools so the tools stay pure functions."""

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from helpdesk.config import DATA_DIR


@dataclass(frozen=True)
class PolicySection:
    source: str  # file name, e.g. "prices.md"
    heading: str
    text: str


def load_bookings(path: Path = DATA_DIR / "bookings.json") -> dict[str, dict]:
    """Return bookings keyed by id. Money is parsed straight into Decimal, never via float."""
    with path.open(encoding="utf-8") as file:
        records = json.load(file, parse_float=Decimal)
    return {record["id"]: record for record in records}


def load_policy_sections(directory: Path = DATA_DIR / "policies") -> list[PolicySection]:
    """Split every policy file into sections at its '## ' headings."""
    sections: list[PolicySection] = []
    for path in sorted(directory.glob("*.md")):
        sections.extend(_split_sections(path.name, path.read_text(encoding="utf-8")))
    return sections


def _split_sections(source: str, markdown: str) -> list[PolicySection]:
    title = ""
    heading = ""
    lines: list[str] = []
    sections: list[PolicySection] = []

    def flush() -> None:
        text = "\n".join(lines).strip()
        if text:
            # Text before the first '## ' (the preamble) is filed under the document title.
            sections.append(PolicySection(source, heading or title, text))

    for line in markdown.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
        elif line.startswith("## "):
            flush()
            heading = line[3:].strip()
            lines = []
        else:
            lines.append(line)
    flush()
    return sections
