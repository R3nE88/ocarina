"""End-to-end check of the API against a real, empty Postgres database.
Run: DATABASE_URL=postgresql://... ADMIN_TOKEN=x pytest server/test_api.py
The tables are wiped first, so never point it at the production database."""
import os

os.environ.setdefault("ADMIN_TOKEN", "test-admin")
os.environ.setdefault("REPORT_THRESHOLD", "3")

import psycopg
import pytest
from fastapi.testclient import TestClient

import main

ADMIN = {"X-Admin-Token": os.environ["ADMIN_TOKEN"]}
SHEET = {"title": "Zelda's Lullaby", "subtitle": "Koji Kondo", "game": "n64",
         "data": {"src": "% Canción — ♪ ゼルダ\nB4:2 D5:4 A4:2 | G4:4", "tempo": 90}}


@pytest.fixture(scope="module")
def client():
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as c:
        c.execute("DROP TABLE IF EXISTS reports, comments, votes, scores, devices")
    with TestClient(main.app) as c:
        yield c


def device(client, name):
    r = client.post("/api/devices", json={"name": name})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}, r.json()["id"]


def test_flow(client):
    alice, alice_id = device(client, "Alice")
    bob, _ = device(client, "Bob")
    assert client.get("/api/me", headers=alice).json()["name"] == "Alice"
    assert client.post("/api/scores", json=SHEET).status_code == 401

    # share, open by link, edit only as owner
    sid = client.post("/api/scores", json=SHEET, headers=alice).json()["id"]
    s = client.get(f"/api/scores/{sid}", headers=bob).json()
    assert s["title"] == "Zelda's Lullaby" and s["data"]["tempo"] == 90 and not s["mine"]
    assert client.put(f"/api/scores/{sid}", json=SHEET, headers=bob).status_code == 404
    assert client.put(f"/api/scores/{sid}", json={**SHEET, "title": "Lullaby"}, headers=alice).status_code == 200
    assert client.post("/api/scores", json={**SHEET, "game": "wii"}, headers=alice).status_code == 422
    assert "<title>Lullaby</title>" in client.get(f"/s/{sid}").text

    # a link-only sheet stays out of the gallery but shows on its owner's profile
    hidden_sid = client.post("/api/scores", json={**SHEET, "title": "Draft", "listed": False}, headers=alice).json()["id"]
    titles = lambda h=None, **p: [i["title"] for i in client.get("/api/scores", params=p, headers=h).json()["items"]]
    assert titles(sort="new") == ["Lullaby"]
    assert set(titles(author=alice_id, h=alice)) == {"Lullaby", "Draft"}
    assert titles(q="lull") == ["Lullaby"] and titles(q="%") == [] and titles(game="3ds") == []

    # likes drive trending and top
    other = client.post("/api/scores", json={**SHEET, "title": "Song of Storms"}, headers=bob).json()["id"]
    assert client.post(f"/api/scores/{other}/like", headers=alice).json() == {"likes": 1, "liked": True}
    client.post(f"/api/scores/{other}/like", headers=alice)  # liking twice counts once
    assert titles(sort="trending")[0] == "Song of Storms"
    assert client.get(f"/api/scores/{other}", headers=alice).json()["liked"] is True
    assert client.delete(f"/api/scores/{other}/like", headers=alice).json()["likes"] == 0

    # comments
    cid = client.post(f"/api/scores/{sid}/comments", json={"body": "  Nice!  "}, headers=bob).json()["id"]
    assert [c["body"] for c in client.get(f"/api/scores/{sid}/comments").json()] == ["Nice!"]
    assert client.post(f"/api/scores/{sid}/comments", json={"body": " "}, headers=bob).status_code == 422
    assert client.delete(f"/api/comments/{cid}", headers=alice).status_code == 404  # not the author

    # three reports from different devices hide the sheet; an admin restores it
    for i in range(3):
        h, _ = device(client, f"r{i}")
        r = client.post("/api/reports", json={"kind": "score", "target": sid, "reason": "spam"}, headers=h).json()
    assert r["hidden"] is True
    assert client.get(f"/api/scores/{sid}", headers=bob).status_code == 404
    assert client.get(f"/api/scores/{sid}", headers=alice).status_code == 200  # the author still sees it
    assert "Lullaby" not in titles(sort="new")
    assert client.get("/api/admin/reports").status_code == 403
    rep = client.get("/api/admin/reports", headers=ADMIN).json()
    assert rep[0]["target"] == sid and rep[0]["reports"] == 3 and rep[0]["hidden"]
    client.post("/api/admin/restore", json={"kind": "score", "target": sid}, headers=ADMIN)
    assert client.get(f"/api/scores/{sid}", headers=bob).status_code == 200

    # comments can be reported too
    h, _ = device(client, "r9")
    assert client.post("/api/reports", json={"kind": "comment", "target": str(cid)}, headers=h).json()["hidden"] is False
    assert client.post("/api/reports", json={"kind": "comment", "target": "x"}, headers=h).status_code == 404

    # a banned device can't write and its sheets disappear
    client.post("/api/admin/ban", json={"device_id": alice_id}, headers=ADMIN)
    assert client.post("/api/scores", json=SHEET, headers=alice).status_code == 403
    assert titles(sort="new") == ["Song of Storms"]

    # admin and owner deletes
    assert client.delete(f"/api/comments/{cid}", headers=ADMIN).status_code == 200
    assert client.delete(f"/api/scores/{other}", headers=bob).status_code == 200
    assert client.get(f"/api/scores/{other}").status_code == 404
    assert client.delete(f"/api/scores/{hidden_sid}", headers=ADMIN).status_code == 200
