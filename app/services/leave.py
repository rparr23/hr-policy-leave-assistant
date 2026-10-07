"""Leave balance, validation, submission and approval.

Every hard rule lives here, not in the model: date validation, business-day
math, overlap detection and balance checks. The agent reads results back.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.services.errors import ServiceError
from app.services.workers import get_employee, hours_per_day
from app.store import now_iso, store, today

ACTIVE_STATUSES = {"pending", "approved"}


def _parse(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ServiceError("bad_date", f"{field} must be a date in yyyy-MM-dd format.", details={"field": field})


def business_days(start: date, end: date) -> list[date]:
    holidays = {date.fromisoformat(d) for d in store.policy["holidays_2026"]}
    days, current = [], start
    while current <= end:
        if current.weekday() < 5 and current not in holidays:
            days.append(current)
        current += timedelta(days=1)
    return days


def pending_hours(email: str, balance_kind: str) -> float:
    kinds = {k for k, v in store.policy["leave_types"].items() if v["uses_balance"] == balance_kind}
    return sum(r["hours"] for r in store.requests_for(email) if r["status"] == "pending" and r["leave_type"] in kinds)


def leave_balance(email: str) -> dict:
    """GetLeaveBalance: booked balance minus hours tied up in pending requests."""
    emp = get_employee(email)
    hpd = hours_per_day(emp)
    out = {}
    for kind, hours in emp["balances_hours"].items():
        held = pending_hours(email, kind)
        available = hours - held
        out[kind] = {
            "balance_hours": hours,
            "pending_hours": held,
            "available_hours": available,
            "available_days": round(available / hpd, 2),
        }
    return {"hours_per_day": hpd, "balances": out}


def _overlaps(email: str, start: date, end: date, exclude_id: str | None = None) -> list[dict]:
    hits = []
    for r in store.requests_for(email):
        if r["status"] not in ACTIVE_STATUSES or r["id"] == exclude_id:
            continue
        if date.fromisoformat(r["start_date"]) <= end and date.fromisoformat(r["end_date"]) >= start:
            hits.append({k: r[k] for k in ("id", "leave_type", "start_date", "end_date", "status")})
    return hits


def check_leave(email: str, leave_type: str, start_date: str, end_date: str) -> dict:
    """CheckLeaveRequest: validate everything without writing anything."""
    emp = get_employee(email)
    types = store.policy["leave_types"]
    problems: list[dict] = []

    if leave_type not in types:
        problems.append({
            "code": "invalid_leave_type",
            "message": f"'{leave_type}' is not a leave type. Choose one of: {', '.join(types)}.",
        })
    start = _parse(start_date, "start_date")
    end = _parse(end_date, "end_date")
    if start < today():
        problems.append({"code": "start_in_past", "message": "The start date is in the past."})
    if end < start:
        problems.append({"code": "end_before_start", "message": "The end date is earlier than the start date."})

    days = business_days(start, end) if end >= start else []
    if end >= start and not days:
        problems.append({"code": "no_working_days", "message": "Those dates contain no working days (weekends and company holidays are excluded)."})
    hours = len(days) * hours_per_day(emp)

    overlaps = _overlaps(email, start, end) if end >= start else []
    if overlaps:
        problems.append({"code": "overlap", "message": "These dates overlap an existing request.", "overlaps": overlaps})

    cfg = types.get(leave_type, {})
    balance_before = balance_after = None
    if cfg.get("uses_balance"):
        available = leave_balance(email)["balances"][cfg["uses_balance"]]["available_hours"]
        balance_before, balance_after = available, available - hours
        if balance_after < 0:
            problems.append({
                "code": "insufficient_balance",
                "message": f"This needs {hours:g} hours but only {available:g} are available.",
            })
    if cfg.get("max_days") and len(days) > cfg["max_days"]:
        problems.append({"code": "over_max_days", "message": f"{cfg['label']} is limited to {cfg['max_days']} days."})

    doc_after = cfg.get("doc_required_after_days")
    return {
        "ok": not problems,
        "problems": problems,
        "leave_type": leave_type,
        "leave_type_label": cfg.get("label"),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "working_days": [d.isoformat() for d in days],
        "days": len(days),
        "hours": hours,
        "available_hours_before": balance_before,
        "available_hours_after": balance_after,
        "requires_hr_case": bool(cfg.get("requires_hr_case")),
        "documentation_required": doc_after is not None and len(days) > doc_after,
        "approver_email": emp["manager_email"],
    }


def submit_leave(email: str, leave_type: str, start_date: str, end_date: str, reason: str, confirmed: bool) -> dict:
    """SubmitLeave: re-validates server-side and refuses without explicit confirmation."""
    if not confirmed:
        raise ServiceError("not_confirmed", "Read the request back to the employee and get an explicit yes before submitting.")
    check = check_leave(email, leave_type, start_date, end_date)
    if not check["ok"]:
        raise ServiceError("invalid_request", "The request did not pass validation.", details={"problems": check["problems"]})
    if check["requires_hr_case"]:
        raise ServiceError("hr_case_required", f"{check['leave_type_label']} is handled by HR. Open an HR case instead.", 409)

    emp = get_employee(email)
    request = {
        "id": store.next_id("LV"),
        "employee_email": emp["email"],
        "leave_type": leave_type,
        "start_date": check["start_date"],
        "end_date": check["end_date"],
        "hours": check["hours"],
        "reason": reason.strip(),
        "status": "pending",
        "approver_email": emp["manager_email"],
        "submitted_at": now_iso(),
    }
    store.leave_requests.append(request)
    store.notify(
        emp["manager_email"],
        f"Leave request {request['id']} from {emp['name']}",
        f"{check['leave_type_label']}: {check['start_date']} to {check['end_date']} ({check['days']} days). Reason: {request['reason']}",
        channel="teams_approval_card",
    )
    return {**request, "days": check["days"], "available_hours_after": check["available_hours_after"],
            "documentation_required": check["documentation_required"]}


def list_requests(email: str, status: str | None = None) -> list[dict]:
    rows = [r for r in store.requests_for(email) if status is None or r["status"] == status]
    return sorted(rows, key=lambda r: r["submitted_at"], reverse=True)


def _own_request(email: str, request_id: str) -> dict:
    for r in store.requests_for(email):
        if r["id"] == request_id:
            return r
    # Same answer whether the request is someone else's or does not exist.
    raise ServiceError("not_found", f"No request {request_id} found for you.", 404)


def cancel_request(email: str, request_id: str) -> dict:
    r = _own_request(email, request_id)
    if r["status"] != "pending":
        raise ServiceError("not_cancellable", f"Only pending requests can be cancelled; {request_id} is {r['status']}.", 409)
    r["status"] = "cancelled"
    store.notify(r["approver_email"], f"Leave request {request_id} cancelled", "The employee cancelled this request.")
    return r


def remind_approver(email: str, request_id: str) -> dict:
    r = _own_request(email, request_id)
    if r["status"] != "pending":
        raise ServiceError("not_pending", f"{request_id} is already {r['status']}; no reminder needed.", 409)
    emp = get_employee(email)
    note = store.notify(
        r["approver_email"],
        f"Reminder: leave request {request_id} is waiting for you",
        f"{emp['name']} asked for {r['start_date']} to {r['end_date']}. Please approve or reject it.",
    )
    return {"request_id": request_id, "reminded": r["approver_email"], "sent_at": note["sent_at"]}


def decide(approver_email: str, request_id: str, decision: str, comment: str = "") -> dict:
    """Called from the manager's approval card, never by the employee's agent."""
    if decision not in {"approved", "rejected"}:
        raise ServiceError("bad_decision", "Decision must be 'approved' or 'rejected'.")
    r = next((x for x in store.leave_requests if x["id"] == request_id), None)
    if not r or r["approver_email"].lower() != approver_email.lower():
        raise ServiceError("not_found", f"No request {request_id} is waiting for your approval.", 404)
    if r["status"] != "pending":
        raise ServiceError("not_pending", f"{request_id} is already {r['status']}.", 409)
    r["status"] = decision
    r["decided_at"] = now_iso()
    r["approver_comment"] = comment
    emp = store.employees[r["employee_email"].lower()]
    if decision == "approved":
        kind = store.policy["leave_types"][r["leave_type"]]["uses_balance"]
        if kind:
            emp["balances_hours"][kind] -= r["hours"]
    store.notify(r["employee_email"], f"Your leave request {request_id} was {decision}", comment or "")
    return r
