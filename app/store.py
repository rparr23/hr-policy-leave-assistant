"""In-memory data store seeded from data/*.json.

Stands in for the HRIS, the time-off tool, SharePoint lists and Dataverse
tables during demos. Swap the methods on `Store` for real connectors in
production; the services only talk to this interface.
"""

from __future__ import annotations

import copy
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path

DATA_DIR = Path(os.environ.get("HR_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))


def _load(name: str):
    with open(DATA_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def today() -> date:
    """Current date; HR_TODAY pins it for demos and tests."""
    pinned = os.environ.get("HR_TODAY")
    return date.fromisoformat(pinned) if pinned else date.today()


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class Store:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.employees: dict[str, dict] = {e["email"].lower(): e for e in _load("employees.json")}
        self.leave_requests: list[dict] = _load("leave_requests.json")
        self.policy: dict = _load("company_policy.json")
        rules = _load("state_leave_rules.json")
        self.state_rules: list[dict] = rules["rules"]
        self.federal_rule: dict = rules["federal"]
        self.employer_headcount: int = rules["employer_headcount"]
        self.travel_requests: list[dict] = []
        self.hr_cases: list[dict] = []
        self.notifications: list[dict] = []
        self._seq = {"LV": 20481, "TR": 5001, "HR": 9001}

    def next_id(self, prefix: str) -> str:
        value = self._seq[prefix]
        self._seq[prefix] += 1
        return f"{prefix}-{value}"

    def employee(self, email: str) -> dict | None:
        found = self.employees.get(email.lower())
        return copy.deepcopy(found) if found else None

    def requests_for(self, email: str) -> list[dict]:
        return [r for r in self.leave_requests if r["employee_email"].lower() == email.lower()]

    def notify(self, to: str, subject: str, body: str, channel: str = "teams") -> dict:
        note = {"to": to, "subject": subject, "body": body, "channel": channel, "sent_at": now_iso()}
        self.notifications.append(note)
        return note


store = Store()
