from tests.conftest import ANA, JAMES, LEE, MARIA, SAM, as_user


def test_state_rule_uses_callers_work_state(client):
    r = client.get("/rules/state", params={"leave_type": "paid_sick"}, headers=as_user(MARIA)).json()
    assert r["found"] and r["state"] == "CA"
    assert r["min_hours_per_year"] == 40
    assert r["source_url"].startswith("https://")
    assert r["needs_verification"] is False


def test_state_can_be_named_explicitly(client):
    r = client.get("/rules/state", params={"leave_type": "family_medical", "state": "wa"}, headers=as_user(MARIA)).json()
    assert r["state"] == "WA"


def test_missing_rule_says_company_policy_applies(client):
    r = client.get("/rules/state", params={"leave_type": "family_medical"}, headers=as_user(ANA)).json()
    assert r["found"] is False and "Company policy applies" in r["message"]


def test_stale_rule_is_flagged(client):
    r = client.get("/rules/state", params={"leave_type": "paid_sick"}, headers=as_user(LEE)).json()
    assert r["needs_verification"] is True


def test_part_time_california_gets_the_state_minimum(client):
    # PRD sample 1: the state minimum beats company policy for part-time staff.
    e = client.get("/leave/sick-entitlement", headers=as_user(MARIA)).json()
    assert e["company_hours_per_year"] == 0
    assert e["state_minimum_hours_per_year"] == 40
    assert e["entitlement_hours_per_year"] == 40
    assert e["applies"] == "state"
    assert e["available_hours"] == 22.5


def test_new_york_minimum_depends_on_employer_size(client):
    e = client.get("/leave/sick-entitlement", headers=as_user(JAMES)).json()
    assert e["state_minimum_hours_per_year"] == 56  # 1,200 employees => 100+ tier
    assert e["entitlement_hours_per_year"] == 56
    assert e["applies"] == "state"


def test_texas_falls_back_to_company_policy(client):
    e = client.get("/leave/sick-entitlement", headers=as_user(ANA)).json()
    assert e["applies"] == "company" and e["entitlement_hours_per_year"] == 48


def test_fmla_and_ny_pfl_eligible(client):
    # PRD sample 3.
    r = client.get("/leave/eligibility", headers=as_user(JAMES)).json()
    assert r["federal"]["eligible"] is True
    assert r["state"]["program"] == "New York Paid Family Leave"
    assert r["state"]["eligible"] is True
    assert "HR confirms" in r["disclaimer"]


def test_new_hire_at_small_site_fails_each_fmla_test(client):
    r = client.get("/leave/eligibility", headers=as_user(ANA)).json()
    assert r["federal"]["eligible"] is False
    assert [c["met"] for c in r["federal"]["checks"]] == [False, False, False]
    assert r["state"]["program"] is None


def test_part_time_california_misses_cfra_hours(client):
    r = client.get("/leave/eligibility", headers=as_user(MARIA)).json()
    hours = next(c for c in r["state"]["checks"] if "hours" in c["criterion"])
    assert hours["met"] is False
    assert r["federal"]["eligible"] is False


def test_washington_pfml(client):
    r = client.get("/leave/eligibility", headers=as_user(SAM)).json()
    assert r["state"]["program"] == "Washington Paid Family and Medical Leave"
    assert r["state"]["eligible"] is True
