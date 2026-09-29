"""Deterministic bilingual advisory drafting and strict template linting."""

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from app.alerts import LEVEL_RANK

IST = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True)
class AdvisoryDraft:
    """A template-bound advisory that cannot be dispatched before approval."""

    alert_level: str
    locality: str
    start_time: datetime
    end_time: datetime
    language: str
    text: str
    template_version: str
    status: str = "pending_approval"


def _templates(path: str | Path = "config/advisory_templates.json") -> dict[str, object]:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if set(document.get("templates", {})) != {"en", "hi"} or not document.get("version"):
        raise ValueError("advisory templates must define versioned English and Hindi text")
    return document


def _format_time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("advisory times must be timezone-aware")
    return value.astimezone(IST).strftime("%d %b %Y %H:%M IST")


def _render(draft: AdvisoryDraft, templates: dict[str, object]) -> str:
    template = templates["templates"][draft.language]
    return template.format(
        level=draft.alert_level.upper(),
        locality=draft.locality,
        start_time=_format_time(draft.start_time),
        end_time=_format_time(draft.end_time),
    )


def draft_advisory(
    alert_level: str,
    locality: str,
    start_time: datetime,
    end_time: datetime,
    language: str,
) -> AdvisoryDraft:
    """Render an approved template using a pre-existing deterministic alert level."""
    if alert_level not in LEVEL_RANK:
        raise ValueError(f"unknown alert level: {alert_level}")
    if language not in {"en", "hi"}:
        raise ValueError(f"unsupported language: {language}")
    if not re.fullmatch(r"[\w .,'()\-]{1,100}", locality, flags=re.UNICODE):
        raise ValueError("locality contains unsupported characters")
    _format_time(start_time)
    _format_time(end_time)
    if end_time <= start_time:
        raise ValueError("advisory end time must follow start time")
    templates = _templates()
    draft = AdvisoryDraft(
        alert_level,
        locality,
        start_time,
        end_time,
        language,
        "",
        str(templates["version"]),
    )
    return AdvisoryDraft(**{**draft.__dict__, "text": _render(draft, templates)})


def lint_advisory(draft: AdvisoryDraft) -> bool:
    """Reject any text or state outside the approved versioned template."""
    templates = _templates()
    if draft.template_version != templates["version"]:
        raise ValueError("draft does not use the current approved template version")
    if draft.status != "pending_approval":
        raise ValueError("new advisory drafts must remain pending approval")
    if draft.text != _render(draft, templates):
        raise ValueError("draft contains content outside the approved template")
    return True
