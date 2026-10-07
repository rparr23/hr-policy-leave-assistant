from __future__ import annotations

from datetime import date

from app.services.errors import ServiceError
from app.store import store, today


def months_between(start: date, end: date) -> int:
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day:
        months -= 1
    return max(months, 0)


def get_employee(email: str) -> dict:
    emp = store.employee(email)
    if not emp:
        raise ServiceError("unknown_employee", "No employee record found for the signed-in user.", 404)
    return emp


def hours_per_day(emp: dict) -> float:
    return float(store.policy["hours_per_day"][emp["employment_type"]])


def worker_profile(email: str) -> dict:
    """GetWorkerProfile: the context every entitlement answer is tailored to."""
    emp = get_employee(email)
    manager = store.employee(emp["manager_email"])
    hire = date.fromisoformat(emp["hire_date"])
    return {
        "name": emp["name"],
        "email": emp["email"],
        "employee_id": emp["employee_id"],
        "work_state": emp["work_state"],
        "employment_type": emp["employment_type"],
        "flsa_status": emp["flsa_status"],
        "hire_date": emp["hire_date"],
        "tenure_months": months_between(hire, today()),
        "weekly_hours": emp["weekly_hours"],
        "union_member": emp["union_member"],
        "cost_center": emp["cost_center"],
        "manager": {"name": manager["name"] if manager else None, "email": emp["manager_email"]},
    }
