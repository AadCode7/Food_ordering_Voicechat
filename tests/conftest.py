import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["LLM_PROVIDER"] = "none"
os.environ["SECRET_KEY"] = "test-secret-key-that-is-long-enough-for-hs256-use"
os.environ["RATE_LIMIT_PER_MIN"] = "1000"
os.environ["AUTH_RATE_LIMIT_PER_MIN"] = "1000"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from api.index import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def auth(client):
    """A freshly signed-up user: returns (headers, email)."""
    import uuid

    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/signup", json={"name": "Test User", "email": email, "password": "supersecret1"})
    assert r.status_code == 201, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}, email
