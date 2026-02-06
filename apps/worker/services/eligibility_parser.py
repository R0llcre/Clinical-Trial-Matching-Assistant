from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

_HEADING_ONLY = re.compile(
    r"^(inclusion(?: criteria)?|exclusion(?: criteria)?)\s*[:\-]?\s*$", re.I
)
_HEADING_WITH_TAIL = re.compile(
    r"^(inclusion(?: criteria)?|exclusion(?: criteria)?)\s*[:\-]\s*(.+)$",
    re.I,
)
_BULLET_PREFIX = re.compile(r"^(?:[-*]\s*|\u2022\s*|\d+[.)]\s*)")
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?;])\s+")
_WHITESPACE = re.compile(r"\s+")


def preprocess_eligibility_text(eligibility_text: Optional[str]) -> Dict[str, List[str]]:
    """Split eligibility text into cleaned inclusion/exclusion sentence lists."""
    if not isinstance(eligibility_text, str) or not eligibility_text.strip():
        return {"inclusion_sentences": [], "exclusion_sentences": []}

    normalized = eligibility_text.replace("\r\n", "\n").replace("\r", "\n")
    inclusion_lines, exclusion_lines, has_heading = _split_sections(normalized)

    if not has_heading:
        return {
            "inclusion_sentences": _split_into_sentences(inclusion_lines),
            "exclusion_sentences": [],
        }

    return {
        "inclusion_sentences": _split_into_sentences(inclusion_lines),
        "exclusion_sentences": _split_into_sentences(exclusion_lines),
    }


def _split_sections(text: str) -> Tuple[List[str], List[str], bool]:
    sections: Dict[str, List[str]] = {"inclusion": [], "exclusion": []}
    preamble: List[str] = []
    current: Optional[str] = None
    has_heading = False

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        heading, heading_tail = _extract_heading(line)
        if heading:
            has_heading = True
            current = heading
            if heading_tail:
                sections[current].append(heading_tail)
            continue

        cleaned = _clean_line(line)
        if not cleaned:
            continue
        if current in sections:
            sections[current].append(cleaned)
        else:
            preamble.append(cleaned)

    if has_heading and preamble:
        sections["inclusion"] = preamble + sections["inclusion"]

    if has_heading:
        return sections["inclusion"], sections["exclusion"], True

    merged = preamble + sections["inclusion"] + sections["exclusion"]
    return merged, [], False


def _extract_heading(line: str) -> Tuple[Optional[str], Optional[str]]:
    inline = _HEADING_WITH_TAIL.match(line)
    if inline:
        section = _section_name(inline.group(1))
        if section:
            tail = _clean_line(inline.group(2))
            return section, tail or None

    only = _HEADING_ONLY.match(line)
    if only:
        section = _section_name(only.group(1))
        if section:
            return section, None

    return None, None


def _section_name(raw_heading: str) -> Optional[str]:
    heading = raw_heading.strip().lower()
    if heading.startswith("inclusion"):
        return "inclusion"
    if heading.startswith("exclusion"):
        return "exclusion"
    return None


def _clean_line(line: str) -> str:
    without_bullet = _BULLET_PREFIX.sub("", line.strip())
    return _WHITESPACE.sub(" ", without_bullet).strip()


def _split_into_sentences(lines: List[str]) -> List[str]:
    sentences: List[str] = []
    for line in lines:
        for part in _SENTENCE_BOUNDARY.split(line):
            cleaned = _clean_line(part)
            if cleaned:
                sentences.append(cleaned)
    return sentences
