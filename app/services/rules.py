"""State leave rules lookup and leave eligibility (FMLA + state programs)."""

from __future__ import annotations

from datetime import date

from app.services.errors import ServiceError
from app.services.workers import get_employee, hours_per_day, months_between
from app.store import store, today

STALE_AFTER_MONTHS = 12
RULE_TYPES = {"paid_sick", "family_medical"}


def _with_freshness(rule: dict) -> dict:
    reviewed = date.fromisoformat(rule["last_reviewed"])
    stale = months_between(reviewed, today()) >= STALE_AFTER_MONTHS
    return {**rule, "needs_verification": stale,
            "freshness_note": "Rule not reviewed in 12+ months; verify with HR." if stale else None}


def lookup_state_rule(email: str, leave_type: str, state: str | None = None) -> dict:
    """LookupStateRule: the rule for the caller's work state unless a state is named."""
    if leave_type not in RULE_TYPES:
        raise ServiceError("bad_leave_type", f"leave_type must be one of: {', '.join(sorted(RULE_TYPES))}.")
    work_state = (state or get_employee(email)["work_state"]).upper()
    rule = next((r for r in store.state_rules if r["state"] == work_state and r["leave_type"] == leave_type), None)
    if not rule:
        return {"state": work_state, "leave_type": leave_type, "found": False,
                "message": f"No {leave_type} rule on file for {work_state}. Company policy applies; check with HR."}
    return {"found": True, **_with_freshness(rule)}


def _state_sick_minimum_hours(rule: dict, emp: dict) -> float:
    if "min_hours_by_headcount" in rule:
        for tier in rule["min_hours_by_headcount"]:
            if store.employer_headcount >= tier["min_employees"]:
                return float(tier["hours"])
        return 0.0
    return float(rule.get("min_hours_per_year", 0))


def sick_entitlement(email: str) -> dict:
    """Company sick days vs the state minimum; the more generous one applies."""
    emp = get_employee(email)
    hpd = hours_per_day(emp)
    company_hours = store.policy["sick_leave_days_per_year"][emp["employment_type"]] * hpd
    rule = lookup_state_rule(email, "paid_sick")
    state_hours = _state_sick_minimum_hours(rule, emp) if rule["found"] else 0.0
    applies = "state" if state_hours > company_hours else "company"
    return {
        "work_state": emp["work_state"],
        "employment_type": emp["employment_type"],
        "company_hours_per_year": company_hours,
        "state_minimum_hours_per_year": state_hours,
        "entitlement_hours_per_year": max(company_hours, state_hours),
        "applies": applies,
        "accrual": rule.get("accrual"),
        "state_rule": rule,
        "available_hours": emp["balances_hours"].get("sick"),
    }


def _check(name: str, met: bool, detail: str) -> dict:
    return {"criterion": name, "met": met, "detail": detail}


def fmla_eligibility(emp: dict) -> dict:
    fed = store.federal_rule
    req = fed["eligibility"]
    tenure = months_between(date.fromisoformat(emp["hire_date"]), today())
    checks = [
        _check("12 months of service", tenure >= req["min_months_service"], f"{tenure} months"),
        _check("1,250 hours in the last 12 months", emp["hours_last_12_months"] >= req["min_hours_12_months"],
               f"{emp['hours_last_12_months']} hours"),
        _check("50 employees within 75 miles", emp["worksite_employees_within_75_miles"] >= req["min_employees_within_75_miles"],
               f"{emp['worksite_employees_within_75_miles']} employees"),
    ]
    return {"program": fed["name"], "eligible": all(c["met"] for c in checks), "checks": checks,
            "job_protected_weeks": fed["job_protected_weeks"], "paid": False, "source_url": fed["source_url"]}


def state_family_eligibility(emp: dict) -> dict:
    rule = next((r for r in store.state_rules if r["state"] == emp["work_state"] and r["leave_type"] == "family_medical"), None)
    if not rule:
        return {"program": None, "eligible": False, "checks": [],
                "message": f"{emp['work_state']} has no state family leave program on file; FMLA and company policy apply."}
    req = rule["eligibility"]
    tenure = months_between(date.fromisoformat(emp["hire_date"]), today())
    tenure_days = (today() - date.fromisoformat(emp["hire_date"])).days
    checks = []
    if "min_months_service" in req:
        checks.append(_check(f"{req['min_months_service']} months of service", tenure >= req["min_months_service"], f"{tenure} months"))
    if "min_hours_12_months" in req:
        checks.append(_check(f"{req['min_hours_12_months']:,} hours in 12 months",
                             emp["hours_last_12_months"] >= req["min_hours_12_months"], f"{emp['hours_last_12_months']} hours"))
    if "min_weeks_if_20_plus_hours" in req:
        if emp["weekly_hours"] >= 20:
            checks.append(_check("26 consecutive weeks (20+ hours a week)", tenure_days >= req["min_weeks_if_20_plus_hours"] * 7,
                                 f"{tenure_days // 7} weeks"))
        else:
            checks.append(_check("175 days worked (under 20 hours a week)", tenure_days >= req["min_days_if_under_20_hours"],
                                 f"{tenure_days} days employed"))
    if "min_hours_qualifying_period" in req:
        checks.append(_check(f"{req['min_hours_qualifying_period']} hours in the qualifying period",
                             emp["hours_last_12_months"] >= req["min_hours_qualifying_period"], f"{emp['hours_last_12_months']} hours"))
    return {"program": rule["name"], "eligible": all(c["met"] for c in checks), "checks": checks,
            "job_protected_weeks": rule.get("job_protected_weeks"), "paid_weeks": rule.get("paid_weeks"),
            "source_url": rule["source_url"], "last_reviewed": rule["last_reviewed"]}


def leave_eligibility(email: str) -> dict:
    """CheckLeaveEligibility: an indication only; HR confirms and opens the case."""
    emp = get_employee(email)
    return {
        "work_state": emp["work_state"],
        "federal": fmla_eligibility(emp),
        "state": state_family_eligibility(emp),
        "disclaimer": "This is an eligibility indication from HR records. HR confirms eligibility and handles the paperwork.",
    }
