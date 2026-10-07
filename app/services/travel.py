"""Travel policy checks and multi-stage approval routing."""

from __future__ import annotations

from datetime import date

from app.services.errors import ServiceError
from app.services.workers import get_employee
from app.store import now_iso, store, today

FINANCE_APPROVER = "finance.approvals@contoso.com"
VP_APPROVER = "vp.operations@contoso.com"


def check_travel(email: str, destination: str, start_date: str, end_date: str, purpose: str,
                 estimated_cost_usd: float, international: bool = False, travel_mode: str = "flight",
                 cabin_class: str = "economy", flight_hours: float = 0) -> dict:
    emp = get_employee(email)
    pol = store.policy["travel"]
    try:
        start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    except ValueError:
        raise ServiceError("bad_date", "Dates must be in yyyy-MM-dd format.")

    problems, exceptions = [], []
    if start < today():
        problems.append({"code": "start_in_past", "message": "The trip starts in the past."})
    if end < start:
        problems.append({"code": "end_before_start", "message": "The return date is earlier than the departure date."})
    if estimated_cost_usd < 0:
        problems.append({"code": "bad_cost", "message": "Estimated cost cannot be negative."})
    if not purpose.strip():
        problems.append({"code": "missing_purpose", "message": "A business purpose is required."})

    notice = (start - today()).days
    if travel_mode == "flight" and notice < pol["flight_advance_notice_days"]:
        exceptions.append({"code": "short_notice",
                           "message": f"Flights should be booked {pol['flight_advance_notice_days']} days ahead; this is {notice} days. A justification is required."})
    if cabin_class != "economy" and flight_hours < pol["business_class_min_flight_hours"]:
        exceptions.append({"code": "cabin_class",
                           "message": f"Business class is allowed only on flights of {pol['business_class_min_flight_hours']}+ hours."})

    chain = [{"step": "manager", "approver": emp["manager_email"]}]
    if estimated_cost_usd > pol["finance_approval_threshold_usd"]:
        chain.append({"step": "finance", "approver": FINANCE_APPROVER})
    if international:
        chain.append({"step": "vp", "approver": VP_APPROVER})

    nights = max((end - start).days, 0)
    per_diem = pol["per_diem_usd"].get(destination, pol["per_diem_usd"]["default"])
    return {
        "ok": not problems,
        "problems": problems,
        "policy_exceptions": exceptions,
        "justification_required": bool(exceptions),
        "approval_chain": chain,
        "per_diem_usd": per_diem,
        "per_diem_total_usd": per_diem * (nights + 1) if end >= start else 0,
        "nights": nights,
    }


def submit_travel(email: str, confirmed: bool, justification: str = "", **trip) -> dict:
    if not confirmed:
        raise ServiceError("not_confirmed", "Read the trip back to the employee and get an explicit yes before submitting.")
    check = check_travel(email, **trip)
    if not check["ok"]:
        raise ServiceError("invalid_request", "The travel request did not pass validation.", details={"problems": check["problems"]})
    if check["justification_required"] and not justification.strip():
        raise ServiceError("justification_required", "This trip has a policy exception; add a justification.",
                           details={"policy_exceptions": check["policy_exceptions"]})
    emp = get_employee(email)
    record = {
        "id": store.next_id("TR"),
        "employee_email": emp["email"],
        **trip,
        "justification": justification.strip(),
        "policy_exceptions": check["policy_exceptions"],
        "approval_chain": [{**s, "status": "pending" if i == 0 else "waiting"} for i, s in enumerate(check["approval_chain"])],
        "status": "pending",
        "cost_center": emp["cost_center"],
        "per_diem_total_usd": check["per_diem_total_usd"],
        "submitted_at": now_iso(),
    }
    store.travel_requests.append(record)
    store.notify(emp["manager_email"], f"Travel request {record['id']} from {emp['name']}",
                 f"{trip['destination']} {trip['start_date']} to {trip['end_date']}, est. ${trip['estimated_cost_usd']:,.0f}",
                 channel="teams_approval_card")
    return record
