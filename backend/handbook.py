"""The policy wording and claims manual, served section by section."""

import re
from pathlib import Path
from typing import Any

DATA = Path(__file__).resolve().parents[1] / "data"
DOCUMENTS = {
    "wording": DATA / "policy_wording.md",
    "manual": DATA / "claims_manual.md",
}
HEADING = re.compile(r"^## (\d+)\. .*$", re.MULTILINE)


def _sections(document: str) -> list[dict[str, Any]]:
    """Split one document into its numbered `## N.` sections, in order."""
    text = DOCUMENTS[document].read_text(encoding="utf-8")
    matches = list(HEADING.finditer(text))
    sections = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        number = match.group(1)
        sections.append(
            {
                "section_id": f"{document}/{number}",
                "document": document,
                "title": match.group(0).removeprefix("## "),
                "text": text[match.start() : end].strip(),
            }
        )
    return sections


def index() -> list[dict[str, str]]:
    """Return every section of both documents as section_id, document, title."""
    return [
        {"section_id": s["section_id"], "document": s["document"], "title": s["title"]}
        for document in DOCUMENTS
        for s in _sections(document)
    ]


def section(section_id: str) -> dict[str, Any] | None:
    """Return one section with its full text, or None if there is no such id."""
    document = section_id.split("/", 1)[0]
    if document not in DOCUMENTS:
        return None
    return next((s for s in _sections(document) if s["section_id"] == section_id), None)
