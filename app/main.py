"""HR Policy & Leave Assistant tools API.

Each operationId is a tool the Copilot Studio agent calls (REST API tool or
custom connector). Identity comes from the signed-in user: Copilot Studio
passes System.User.Email in the X-User-Email header. In production, put
this API behind Entra ID OAuth on the custom connector so the identity is
taken from the token and cannot be supplied by the caller.
"""

from __future__ import annotations

import os
import secrets
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.services import cases, leave, rules, travel, workers
from app.services.errors import ServiceError

app = FastAPI(
    title="HR Policy & Leave Assistant Tools API",
    version="1.0.0",
    description="Tools for the Copilot Studio HR Policy & Leave Assistant: worker context, leave, state rules, travel and HR handoff.",
)

LeaveType = Literal["annual", "sick", "bereavement", "jury_duty", "unpaid", "parental", "medical"]


@app.exception_handler(ServiceError)
async def service_error_handler(_: Request, exc: ServiceError):
    return JSONResponse(status_code=exc.status, content={"error": exc.code, "message": exc.message, **exc.details})


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    expected = os.environ.get("HR_API_KEY")
    if expected and not (x_api_key and secrets.compare_digest(x_api_key, expected)):
        raise HTTPException(status_code=401, detail="Missing or invalid API key.")


def current_user(
    x_user_email: str = Header(..., description="Signed-in user's email (System.User.Email)."),
    _: None = Depends(require_api_key),
) -> str:
    return x_user_email.strip().lower()


# ---------- request bodies ----------

class LeaveCheckBody(BaseModel):
    leave_type: LeaveType = Field(description="Leave type value exactly as listed.")
    start_date: str = Field(description="First day of leave, yyyy-MM-dd.")
    end_date: str = Field(description="Last day of leave, yyyy-MM-dd.")


class LeaveSubmitBody(LeaveCheckBody):
    reason: str = Field(description="Short reason in the employee's words.")
    confirmed: bool = Field(description="True only if the employee said yes to the read-back in this turn.")


class DecisionBody(BaseModel):
    decision: Literal["approved", "rejected"]
    comment: str = ""


class TravelBody(BaseModel):
    destination: str = Field(description="City of the trip, e.g. Chicago.")
    start_date: str = Field(description="Departure date, yyyy-MM-dd.")
    end_date: str = Field(description="Return date, yyyy-MM-dd.")
    purpose: str = Field(description="Business purpose of the trip.")
    estimated_cost_usd: float = Field(description="Estimated total cost in US dollars.")
    international: bool = False
    travel_mode: Literal["flight", "train", "car"] = "flight"
    cabin_class: Literal["economy", "premium_economy", "business"] = "economy"
    flight_hours: float = Field(default=0, description="Longest flight leg in hours.")


class TravelSubmitBody(TravelBody):
    confirmed: bool = Field(description="True only if the employee said yes to the read-back in this turn.")
    justification: str = Field(default="", description="Reason for any policy exception.")


class TriageBody(BaseModel):
    text: str = Field(description="The employee's message.")


class CaseBody(BaseModel):
    category: str = Field(description="One of: leave, benefits, policy_question, travel, other, or a sensitive topic from ClassifyHRTopic.")
    question: str = Field(description="The employee's exact question.")
    summary: str = ""
    transcript: str = ""


# ---------- routes ----------

@app.get("/health", operation_id="Health", tags=["system"])
def health():
    return {"status": "ok"}


@app.get("/workers/me", operation_id="GetWorkerProfile", tags=["worker"])
def get_worker_profile(user: str = Depends(current_user)):
    """Work state, employment type, tenure and manager for the signed-in employee."""
    return workers.worker_profile(user)


@app.get("/leave/balance", operation_id="GetLeaveBalance", tags=["leave"])
def get_leave_balance(user: str = Depends(current_user)):
    """Leave balances in hours and days, net of pending requests."""
    return leave.leave_balance(user)


@app.get("/leave/sick-entitlement", operation_id="GetSickLeaveEntitlement", tags=["leave"])
def get_sick_entitlement(user: str = Depends(current_user)):
    """Company sick leave vs the work-state minimum; the more generous applies."""
    return rules.sick_entitlement(user)


@app.post("/leave/check", operation_id="CheckLeaveRequest", tags=["leave"])
def check_leave(body: LeaveCheckBody, user: str = Depends(current_user)):
    """Validate dates, working days, overlaps and balance. Writes nothing."""
    return leave.check_leave(user, body.leave_type, body.start_date, body.end_date)


@app.post("/leave/requests", operation_id="SubmitLeave", tags=["leave"], status_code=201)
def submit_leave(body: LeaveSubmitBody, user: str = Depends(current_user)):
    """Submit a validated, confirmed leave request and notify the approver."""
    return leave.submit_leave(user, body.leave_type, body.start_date, body.end_date, body.reason, body.confirmed)


@app.get("/leave/requests", operation_id="GetLeaveRequests", tags=["leave"])
def get_leave_requests(status: Literal["pending", "approved", "rejected", "cancelled"] | None = None,
                       user: str = Depends(current_user)):
    """The signed-in employee's own leave requests, newest first."""
    return {"requests": leave.list_requests(user, status)}


@app.post("/leave/requests/{request_id}/cancel", operation_id="CancelLeave", tags=["leave"])
def cancel_leave(request_id: str, user: str = Depends(current_user)):
    return leave.cancel_request(user, request_id)


@app.post("/leave/requests/{request_id}/remind", operation_id="NotifyApprover", tags=["leave"])
def remind_approver(request_id: str, user: str = Depends(current_user)):
    """Nudge the approver on a pending request."""
    return leave.remind_approver(user, request_id)


@app.post("/leave/requests/{request_id}/decision", operation_id="DecideLeave", tags=["approvals"])
def decide_leave(request_id: str, body: DecisionBody, user: str = Depends(current_user)):
    """Manager approval card callback. Not exposed to the employee agent."""
    return leave.decide(user, request_id, body.decision, body.comment)


@app.get("/rules/state", operation_id="LookupStateRule", tags=["rules"])
def lookup_state_rule(leave_type: Literal["paid_sick", "family_medical"], state: str | None = None,
                      user: str = Depends(current_user)):
    """State leave rule for the employee's work state (or a named state), with source and review date."""
    return rules.lookup_state_rule(user, leave_type, state)


@app.get("/leave/eligibility", operation_id="CheckLeaveEligibility", tags=["rules"])
def check_eligibility(user: str = Depends(current_user)):
    """FMLA and state family/medical leave eligibility indication."""
    return rules.leave_eligibility(user)


@app.post("/travel/check", operation_id="CheckTravelRequest", tags=["travel"])
def check_travel(body: TravelBody, user: str = Depends(current_user)):
    """Apply travel policy and show the approval chain. Writes nothing."""
    return travel.check_travel(user, **body.model_dump())


@app.post("/travel/requests", operation_id="SubmitTravelRequest", tags=["travel"], status_code=201)
def submit_travel(body: TravelSubmitBody, user: str = Depends(current_user)):
    data = body.model_dump()
    return travel.submit_travel(user, confirmed=data.pop("confirmed"), justification=data.pop("justification"), **data)


@app.post("/hr/triage", operation_id="ClassifyHRTopic", tags=["handoff"])
def classify(body: TriageBody, _: str = Depends(current_user)):
    """Is this a sensitive topic the agent must hand to a human?"""
    return cases.triage(body.text)


@app.post("/hr/cases", operation_id="CreateHRCase", tags=["handoff"], status_code=201)
def create_case(body: CaseBody, user: str = Depends(current_user)):
    """Open an HR case with the question, employee context and transcript."""
    return cases.create_case(user, body.category, body.question, body.summary, body.transcript)
