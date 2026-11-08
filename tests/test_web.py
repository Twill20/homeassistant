import os

import pytest
from fastapi.testclient import TestClient

from homerhythm import db
from homerhythm.web import create_app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("HOMERHYTHM_NOW", "2026-11-17T13:20")  # Tuesday, during Gigi's nap
    app = create_app(db.connect(":memory:"))
    return TestClient(app)


def test_pages_render(client):
    for path in ("/", "/week", "/summary", "/settings", "/task/new", "/day/2026-11-20"):
        r = client.get(path)
        assert r.status_code == 200, path
    assert "Bedrooms" in client.get("/").text


def test_check_off_and_move(client):
    client.get("/")  # builds the week
    conn = client.app.state.conn
    it = conn.execute("SELECT id FROM item WHERE date='2026-11-17' AND slot_id IS NOT NULL AND status='planned' "
                      "LIMIT 1").fetchone()["id"]
    assert client.post(f"/item/{it}/toggle", follow_redirects=False).status_code == 303
    assert conn.execute("SELECT status FROM item WHERE id=?", (it,)).fetchone()[0] == "done"
    it2 = conn.execute("SELECT id FROM item WHERE date='2026-11-18' AND status='planned' LIMIT 1").fetchone()["id"]
    client.post(f"/item/{it2}/move", data={"to": "tray"})
    assert conn.execute("SELECT date FROM item WHERE id=?", (it2,)).fetchone()[0] is None
    client.post(f"/item/{it2}/move", data={"to": "2026-11-19|gigi_nap"})
    assert conn.execute("SELECT slot_id FROM item WHERE id=?", (it2,)).fetchone()[0] == "gigi_nap"


def test_anchor_and_settings(client):
    client.post("/anchor/gigi_nap")
    assert "✓ Gigi is down" in client.get("/").text
    r = client.post("/settings/slots", data={"lunchtime__present": "1", "lunchtime__wd_on": "on",
                                             "lunchtime__wd_start": "12:15", "lunchtime__wd_minutes": "25"})
    assert r.status_code == 200
    row = client.app.state.conn.execute("SELECT wd_start, wd_minutes, we_on FROM slot WHERE id='lunchtime'").fetchone()
    assert tuple(row) == ("12:15", 25, 0)
