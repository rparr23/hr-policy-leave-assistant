"""Sensitive-topic triage and HR case creation for human handoff."""

from __future__ import annotations

import re

from app.services.errors import ServiceError
from app.services.workers import get_employee
from app.store import now_iso, store

# Topics the agent must never advise on. Matching is deliberately broad:
# a false positive costs one handoff, a false negative can cost much more.
SENSITIVE_TOPICS = {
    "harassment_discrimination": r"harass|discriminat|hostile|bully|retaliat|inappropriate (comment|touch|behavio)",
    "medical": r"diagnos|medical condition|surgery|cancer|pregnan|mental health|disabilit",
    "accommodation": r"accommodat|\bada\b|reasonable adjust",
    "termination": r"fired|terminat|laid off|layoff|let go|resign",
    "pay_dispute": r"underpaid|not paid|unpaid wages|overtime (pay|owed)|paycheck (wrong|missing)|wage claim",
    "immigration": r"visa|h-?1b|green card|work permit|immigration",
    "safety": r"unsafe|injur|threat|violence|weapon",
}
CATEGORIES = set(SENSITIVE_TOPICS) | {"leave", "benefits", "policy_question", "travel", "other"}


def triage(text: str) -> dict:
    """ClassifyHRTopic: decide whether the agent may answer or must hand off."""
    lowered = text.lower()
    hits = [topic for topic, pattern in SENSITIVE_TOPICS.items() if re.search(pattern, lowered)]
    return {"sensitive": bool(hits), "topics": hits, "action": "handoff" if hits else "answer"}


def create_case(email: str, category: str, question: str, summary: str = "", transcript: str = "") -> dict:
    """CreateHRCase: carries the question, employee context and transcript to a human."""
    if category not in CATEGORIES:
        raise ServiceError("bad_category", f"category must be one of: {', '.join(sorted(CATEGORIES))}.")
    if not question.strip():
        raise ServiceError("missing_question", "Include the employee's question.")
    emp = get_employee(email)
    sensitive = category in SENSITIVE_TOPICS or triage(question)["sensitive"]
    priority = "high" if sensitive else "normal"
    case = {
        "id": store.next_id("HR"),
        "employee_email": emp["email"],
        "employee_context": {k: emp[k] for k in ("name", "work_state", "employment_type", "hire_date", "manager_email")},
        "category": category,
        "priority": priority,
        "sla_hours": store.policy["case_sla_hours"][priority],
        "question": question.strip(),
        "summary": summary.strip(),
        "transcript": transcript,
        "status": "open",
        "created_at": now_iso(),
    }
    store.hr_cases.append(case)
    store.notify("hr.partners@contoso.com", f"[{priority.upper()}] HR case {case['id']}: {category}", question.strip())
    return {k: v for k, v in case.items() if k != "transcript"}
