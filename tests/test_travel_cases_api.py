import json
from pathlib import Path

from tests.conftest import JAMES, MARIA, PRIYA, as_user

TRIP = {"destination": "Chicago", "start_date": "2026-10-13", "end_date": "2026-10-15",
        "purpose": "Client workshop", "estimated_cost_usd": 3000}


def test_short_notice_flight_needs_justification_and_finance(client):
    # PRD sample 4: a flight 6 days out.
    r = client.post("/travel/check", headers=as_user(MARIA), json=TRIP).json()
    assert r["ok"] is True
    assert [e["code"] for e in r["policy_exceptions"]] == ["short_notice"]
    assert [s["step"] for s in r["approval_chain"]] == ["manager", "finance"]
    assert r["approval_chain"][0]["approver"] == PRIYA
    assert r["per_diem_total_usd"] == 85 * 3


def test_business_class_on_short_flight_is_an_exception(client):
    trip = {**TRIP, "start_date": "2026-11-16", "end_date": "2026-11-18", "cabin_class": "business", "flight_hours": 2.5}
    r = client.post("/travel/check", headers=as_user(MARIA), json=trip).json()
    assert [e["code"] for e in r["policy_exceptions"]] == ["cabin_class"]


def test_international_adds_vp_and_cheap_trip_skips_finance(client):
    trip = {**TRIP, "destination": "London", "start_date": "2026-11-16", "end_date": "2026-11-20",
            "estimated_cost_usd": 1800, "international": True}
    r = client.post("/travel/check", headers=as_user(JAMES), json=trip).json()
    assert [s["step"] for s in r["approval_chain"]] == ["manager", "vp"]
    assert r["policy_exceptions"] == []


def test_travel_submit_needs_confirmation_and_justification(client):
    assert client.post("/travel/requests", headers=as_user(MARIA), json={**TRIP, "confirmed": False}).json()["error"] == "not_confirmed"
    missing = client.post("/travel/requests", headers=as_user(MARIA), json={**TRIP, "confirmed": True})
    assert missing.status_code == 400 and missing.json()["error"] == "justification_required"
    ok = client.post("/travel/requests", headers=as_user(MARIA),
                     json={**TRIP, "confirmed": True, "justification": "Client moved the workshop up a week"})
    assert ok.status_code == 201
    rec = ok.json()
    assert rec["id"] == "TR-5001" and rec["cost_center"] == "CC-410"
    assert [s["status"] for s in rec["approval_chain"]] == ["pending", "waiting"]


def test_sensitive_topics_hand_off(client):
    def triage(text):
        return client.post("/hr/triage", headers=as_user(MARIA), json={"text": text}).json()

    assert triage("My manager keeps making inappropriate comments and harassing me")["action"] == "handoff"
    assert "accommodation" in triage("I need an ADA accommodation for my desk")["topics"]
    assert triage("Can I get a visa letter?")["topics"] == ["immigration"]
    assert triage("How many PTO days do I have left?")["action"] == "answer"
    assert triage("Can I fly to Canada for the Nevada office trip?")["action"] == "answer"


def test_case_carries_context_and_sets_priority(client):
    r = client.post("/hr/cases", headers=as_user(JAMES), json={
        "category": "leave", "question": "My wife is having a baby in March. What leave can I take?",
        "summary": "FMLA and NY PFL look eligible", "transcript": "..."})
    assert r.status_code == 201
    case = r.json()
    assert case["priority"] == "normal" and case["sla_hours"] == 24
    assert case["employee_context"]["work_state"] == "NY"
    assert "transcript" not in case
    urgent = client.post("/hr/cases", headers=as_user(MARIA),
                         json={"category": "other", "question": "I am being harassed by a coworker"}).json()
    assert urgent["priority"] == "high" and urgent["sla_hours"] == 4
    bad = client.post("/hr/cases", headers=as_user(MARIA), json={"category": "gossip", "question": "x"})
    assert bad.status_code == 400


def test_identity_header_is_required(client):
    assert client.get("/workers/me").status_code == 422


def test_api_key_enforced_when_configured(client, monkeypatch):
    monkeypatch.setenv("HR_API_KEY", "s3cret")
    assert client.get("/workers/me", headers=as_user(MARIA)).status_code == 401
    ok = client.get("/workers/me", headers={**as_user(MARIA), "X-API-Key": "s3cret"})
    assert ok.status_code == 200
    assert client.get("/health").status_code == 200


def test_openapi_exposes_every_agent_tool(client):
    spec = client.get("/openapi.json").json()
    ops = {op["operationId"] for path in spec["paths"].values() for op in path.values()}
    expected = {"GetWorkerProfile", "GetLeaveBalance", "GetSickLeaveEntitlement", "CheckLeaveRequest", "SubmitLeave",
                "GetLeaveRequests", "CancelLeave", "NotifyApprover", "LookupStateRule", "CheckLeaveEligibility",
                "CheckTravelRequest", "SubmitTravelRequest", "ClassifyHRTopic", "CreateHRCase"}
    assert expected <= ops


def test_committed_openapi_spec_is_current(client):
    committed = json.loads((Path(__file__).parent.parent / "copilot-studio" / "openapi.json").read_text())
    assert committed == client.get("/openapi.json").json(), "Run: python scripts/export_openapi.py"


def test_skill_files_only_reference_real_tools(client):
    spec = client.get("/openapi.json").json()
    ops = {op["operationId"] for path in spec["paths"].values() for op in path.values()}
    skills_dir = Path(__file__).parent.parent / "copilot-studio" / "skills"
    skill_files = sorted(skills_dir.glob("*.md"))
    assert len(skill_files) == 6
    for f in skill_files:
        text = f.read_text()
        assert text.startswith("---\nname: "), f"{f.name} needs YAML front matter"
        for line in text.splitlines():
            if line.startswith("- tool: "):
                assert line.removeprefix("- tool: ").strip() in ops, f"{f.name}: unknown tool in '{line}'"


def test_evaluation_set_names_real_skills_and_tools(client):
    import csv
    spec = client.get("/openapi.json").json()
    ops = {op["operationId"] for path in spec["paths"].values() for op in path.values()}
    root = Path(__file__).parent.parent / "copilot-studio"
    skills = {f.stem for f in (root / "skills").glob("*.md")}
    with open(root / "evaluation-set.csv", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) >= 10
    for row in rows:
        assert row["expected_skill"] in skills, row
        for tool in filter(None, row["expected_tools"].split(";")):
            assert tool in ops, row
