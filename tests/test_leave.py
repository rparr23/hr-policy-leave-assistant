from tests.conftest import ANA, DAVID, JAMES, MARIA, PRIYA, as_user


def check(client, user, leave_type, start, end):
    r = client.post("/leave/check", headers=as_user(user),
                    json={"leave_type": leave_type, "start_date": start, "end_date": end})
    assert r.status_code == 200
    return r.json()


def codes(result):
    return {p["code"] for p in result["problems"]}


def test_worker_profile_comes_from_signed_in_user(client):
    r = client.get("/workers/me", headers=as_user(MARIA))
    body = r.json()
    assert body["work_state"] == "CA"
    assert body["employment_type"] == "part_time"
    assert body["manager"] == {"name": "Priya Shah", "email": PRIYA}
    assert body["tenure_months"] == 43


def test_unknown_user_is_rejected(client):
    r = client.get("/workers/me", headers=as_user("stranger@example.com"))
    assert r.status_code == 404
    assert r.json()["error"] == "unknown_employee"


def test_balance_nets_out_pending_requests(client):
    b = client.get("/leave/balance", headers=as_user(JAMES)).json()["balances"]["annual"]
    assert b == {"balance_hours": 72, "pending_hours": 24, "available_hours": 48, "available_days": 6.0}


def test_friday_and_monday_counts_two_working_days(client):
    # PRD sample 2: Fri 16 Oct and Mon 19 Oct, part-time employee on 4-hour days.
    res = check(client, MARIA, "annual", "2026-10-16", "2026-10-19")
    assert res["ok"] is True
    assert res["working_days"] == ["2026-10-16", "2026-10-19"]
    assert res["hours"] == 8
    assert (res["available_hours_before"], res["available_hours_after"]) == (40, 32)
    assert res["approver_email"] == PRIYA


def test_past_and_inverted_dates_are_refused(client):
    assert "start_in_past" in codes(check(client, MARIA, "annual", "2026-10-01", "2026-10-02"))
    assert "end_before_start" in codes(check(client, MARIA, "annual", "2026-10-20", "2026-10-19"))


def test_bad_date_format_is_explained(client):
    r = client.post("/leave/check", headers=as_user(MARIA),
                    json={"leave_type": "annual", "start_date": "next Friday", "end_date": "2026-10-19"})
    assert r.status_code == 400
    assert r.json()["error"] == "bad_date"


def test_holidays_and_weekends_are_not_working_days(client):
    res = check(client, JAMES, "annual", "2026-11-26", "2026-11-29")  # Thanksgiving Thu-Fri + weekend
    assert "no_working_days" in codes(res)


def test_overlap_with_existing_request(client):
    res = check(client, JAMES, "annual", "2026-10-27", "2026-10-27")
    assert "overlap" in codes(res)
    overlap = next(p for p in res["problems"] if p["code"] == "overlap")
    assert overlap["overlaps"][0]["id"] == "LV-20400"


def test_insufficient_balance(client):
    res = check(client, ANA, "annual", "2026-10-12", "2026-10-14")  # 24h needed, 16h held
    assert "insufficient_balance" in codes(res)


def test_bereavement_capped_and_sick_doc_flag(client):
    assert "over_max_days" in codes(check(client, JAMES, "bereavement", "2026-10-12", "2026-10-19"))
    assert check(client, JAMES, "sick", "2026-10-12", "2026-10-15")["documentation_required"] is True
    assert check(client, JAMES, "sick", "2026-10-12", "2026-10-13")["documentation_required"] is False


def test_submit_requires_explicit_confirmation(client):
    body = {"leave_type": "annual", "start_date": "2026-10-16", "end_date": "2026-10-19",
            "reason": "Family wedding", "confirmed": False}
    r = client.post("/leave/requests", headers=as_user(MARIA), json=body)
    assert r.status_code == 400
    assert r.json()["error"] == "not_confirmed"


def test_submit_creates_request_and_notifies_manager(client):
    from app.store import store
    body = {"leave_type": "annual", "start_date": "2026-10-16", "end_date": "2026-10-19",
            "reason": "Family wedding", "confirmed": True}
    r = client.post("/leave/requests", headers=as_user(MARIA), json=body)
    assert r.status_code == 201
    created = r.json()
    assert created["id"] == "LV-20481"
    assert created["status"] == "pending"
    assert created["available_hours_after"] == 32
    assert store.notifications[-1]["to"] == PRIYA
    # Same dates again now overlap the new request.
    again = client.post("/leave/requests", headers=as_user(MARIA), json=body)
    assert again.status_code == 400
    assert again.json()["problems"][0]["code"] == "overlap"


def test_parental_leave_routes_to_hr(client):
    body = {"leave_type": "parental", "start_date": "2027-03-01", "end_date": "2027-05-21",
            "reason": "New baby", "confirmed": True}
    r = client.post("/leave/requests", headers=as_user(JAMES), json=body)
    assert r.status_code == 409
    assert r.json()["error"] == "hr_case_required"


def test_requests_are_private_to_their_owner(client):
    own = client.get("/leave/requests", headers=as_user(JAMES)).json()["requests"]
    assert [r["id"] for r in own] == ["LV-20400"]
    assert client.get("/leave/requests", headers=as_user(MARIA)).json()["requests"][0]["id"] == "LV-20401"
    # Maria cannot remind about, or cancel, James's request.
    assert client.post("/leave/requests/LV-20400/remind", headers=as_user(MARIA)).status_code == 404
    assert client.post("/leave/requests/LV-20400/cancel", headers=as_user(MARIA)).status_code == 404


def test_remind_only_pending(client):
    ok = client.post("/leave/requests/LV-20400/remind", headers=as_user(JAMES))
    assert ok.status_code == 200 and ok.json()["reminded"] == PRIYA
    done = client.post("/leave/requests/LV-20401/remind", headers=as_user(MARIA))
    assert done.status_code == 409


def test_cancel_frees_balance(client):
    assert client.post("/leave/requests/LV-20400/cancel", headers=as_user(JAMES)).json()["status"] == "cancelled"
    b = client.get("/leave/balance", headers=as_user(JAMES)).json()["balances"]["annual"]
    assert b["available_hours"] == 72


def test_only_the_assigned_manager_can_decide(client):
    wrong = client.post("/leave/requests/LV-20400/decision", headers=as_user(DAVID), json={"decision": "approved"})
    assert wrong.status_code == 404
    right = client.post("/leave/requests/LV-20400/decision", headers=as_user(PRIYA),
                        json={"decision": "approved", "comment": "Enjoy"})
    assert right.json()["status"] == "approved"
    b = client.get("/leave/balance", headers=as_user(JAMES)).json()["balances"]["annual"]
    assert (b["balance_hours"], b["pending_hours"], b["available_hours"]) == (48, 0, 48)
    again = client.post("/leave/requests/LV-20400/decision", headers=as_user(PRIYA), json={"decision": "rejected"})
    assert again.status_code == 409
