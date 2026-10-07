import os

os.environ["HR_TODAY"] = "2026-10-07"  # Wednesday; pins every date-based rule

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.store import store

MARIA = "maria.lopez@contoso.com"   # CA, part-time, 4h days
JAMES = "james.carter@contoso.com"  # NY, full-time, has pending LV-20400
ANA = "ana.nguyen@contoso.com"      # TX, new hire, small worksite
SAM = "sam.patel@contoso.com"       # WA
LEE = "lee.wong@contoso.com"        # IL, stale state rule
PRIYA = "priya.shah@contoso.com"    # manager of Maria and James
DAVID = "david.kim@contoso.com"     # manager of Ana, Sam, Lee


@pytest.fixture(autouse=True)
def fresh_store(monkeypatch):
    monkeypatch.delenv("HR_API_KEY", raising=False)
    store.reset()
    yield


@pytest.fixture
def client():
    return TestClient(app)


def as_user(email):
    return {"X-User-Email": email}
