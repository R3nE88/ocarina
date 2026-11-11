"""API of the ocarina sheet community, and server of the static site (site/)."""
import hashlib
import html
import os
import re
import secrets
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, Field, StringConstraints

HERE = Path(__file__).resolve().parent
SITE = Path(os.environ.get("SITE_DIR", HERE.parent / "site"))
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")
REPORT_THRESHOLD = int(os.environ.get("REPORT_THRESHOLD", "3"))
PAGE_SIZE = 24

pool = ConnectionPool(os.environ["DATABASE_URL"], kwargs={"row_factory": dict_row, "autocommit": True},
                      check=ConnectionPool.check_connection, open=False)  # check: survive a database restart


@asynccontextmanager
async def lifespan(app):
    pool.open(wait=True, timeout=60)
    with pool.connection() as c:
        c.execute((HERE / "schema.sql").read_text("utf-8"))
    yield
    pool.close()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)


def q(sql, params=None):
    with pool.connection() as c:
        cur = c.execute(sql, params)
        return cur.fetchall() if cur.description else []


def q1(sql, params=None):
    rows = q(sql, params)
    return rows[0] if rows else None


# ---------- identity: one secret token per browser ----------

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def current_device(authorization: str | None = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return q1("SELECT id, name, banned FROM devices WHERE token_hash = %s", (hash_token(authorization[7:]),))


def require_device(d=Depends(current_device)):
    if not d:
        raise HTTPException(401, "device")
    if d["banned"]:
        raise HTTPException(403, "banned")
    return d


def is_admin(x_admin_token: str | None = Header(None)) -> bool:
    return bool(ADMIN_TOKEN) and bool(x_admin_token) and secrets.compare_digest(x_admin_token, ADMIN_TOKEN)


def require_admin(admin: bool = Depends(is_admin)):
    if not admin:
        raise HTTPException(403, "admin")


_hits: dict[str, deque] = defaultdict(deque)


def rate(key: str, n: int, per: int = 3600):
    # shortcut: counts live in this process only; move them to Postgres or Redis before running several replicas
    now, d = time.monotonic(), _hits[key]
    while d and d[0] < now - per:
        d.popleft()
    if len(d) >= n:
        raise HTTPException(429, "rate")
    d.append(now)


def new_id() -> str:
    return secrets.token_urlsafe(6)  # 8 URL-safe characters


Text = lambda lo, hi: Annotated[str, StringConstraints(strip_whitespace=True, min_length=lo, max_length=hi)]


class DeviceIn(BaseModel):
    name: Text(1, 40)


@app.post("/api/devices")
def create_device(body: DeviceIn, request: Request):
    rate(f"dev:{request.client.host}", 10)
    token = secrets.token_urlsafe(32)
    d = q1("INSERT INTO devices (id, token_hash, name) VALUES (%s, %s, %s) RETURNING id, name",
           (new_id(), hash_token(token), body.name))
    return {**d, "token": token}


@app.get("/api/me")
def me(d=Depends(current_device)):
    if not d:
        raise HTTPException(401, "device")
    return d


@app.get("/api/devices/{did}")
def public_device(did: str):
    d = q1("SELECT id, name FROM devices WHERE id = %s AND NOT banned", (did,))
    if not d:
        raise HTTPException(404, "missing")
    return d


@app.patch("/api/me")
def rename(body: DeviceIn, d=Depends(require_device)):
    return q1("UPDATE devices SET name = %s WHERE id = %s RETURNING id, name, banned", (body.name, d["id"]))


# ---------- scores ----------

class ScoreData(BaseModel):
    src: str = Field(max_length=20000)
    transpose: str = Field("auto", pattern=r"^(auto|-?\d{1,2})$")
    mpl: int = Field(0, ge=0, le=8)
    tempo: int = Field(110, ge=30, le=300)
    names: bool = False
    bars: bool = False
    ledger: bool = False
    fold: bool = True


class ScoreIn(BaseModel):
    title: Text(1, 120)
    subtitle: Text(0, 120) = ""
    game: Literal["n64", "3ds", "sw2", "real"]
    listed: bool = True
    data: ScoreData


LIKES = "(SELECT count(*) FROM votes v WHERE v.score_id = s.id)"
SUMMARY = f"""SELECT s.id, s.title, s.subtitle, s.game, s.listed, s.created_at, d.id AS author_id, d.name AS author_name,
  {LIKES} AS likes, (SELECT count(*) FROM comments c WHERE c.score_id = s.id AND NOT c.hidden) AS comments
  FROM scores s JOIN devices d ON d.id = s.device_id"""
ORDER = {
    "trending": "(SELECT count(*) FROM votes v WHERE v.score_id = s.id AND v.created_at > now() - interval '7 days') DESC, likes DESC, s.created_at DESC",
    "top": "likes DESC, s.created_at DESC",
    "new": "s.created_at DESC",
}


@app.get("/api/scores")
def list_scores(sort: Literal["trending", "top", "new"] = "trending", search: str = Query("", alias="q"),
                game: str = "", author: str = "", offset: int = 0, d=Depends(current_device)):
    where, p = ["NOT s.hidden", "NOT d.banned"], {}
    if author:
        where.append("s.device_id = %(author)s")
        p["author"] = author
    if not (author and d and d["id"] == author):  # your own profile also lists your link-only sheets
        where.append("s.listed")
    if search.strip():
        where.append(r"(s.title ILIKE %(q)s OR s.subtitle ILIKE %(q)s)")  # shortcut: sequential scan, add pg_trgm past ~100k sheets
        p["q"] = "%" + re.sub(r"([%_\\])", r"\\\1", search.strip()[:100]) + "%"
    if game:
        where.append("s.game = %(game)s")
        p["game"] = game
    p["offset"] = max(0, offset)
    rows = q(f"{SUMMARY} WHERE {' AND '.join(where)} ORDER BY {ORDER[sort]} LIMIT {PAGE_SIZE + 1} OFFSET %(offset)s", p)
    return {"items": rows[:PAGE_SIZE], "more": len(rows) > PAGE_SIZE}


def visible_score(sid: str, d, admin: bool):
    s = q1(f"""SELECT s.*, d.name AS author_name, d.banned AS author_banned, {LIKES} AS likes,
               EXISTS (SELECT 1 FROM votes v WHERE v.score_id = s.id AND v.device_id = %(me)s) AS liked
               FROM scores s JOIN devices d ON d.id = s.device_id WHERE s.id = %(id)s""",
           {"id": sid, "me": d["id"] if d else None})
    if not s:
        raise HTTPException(404, "missing")
    s["mine"] = bool(d) and d["id"] == s["device_id"]
    if (s["hidden"] or s["author_banned"]) and not (s["mine"] or admin):
        raise HTTPException(404, "hidden")
    return s


@app.get("/api/scores/{sid}")
def get_score(sid: str, d=Depends(current_device), admin: bool = Depends(is_admin)):
    s = visible_score(sid, d, admin)
    s["author_id"] = s.pop("device_id")
    del s["author_banned"]
    return s


@app.post("/api/scores")
def create_score(body: ScoreIn, d=Depends(require_device)):
    rate(f"score:{d['id']}", 30)
    return q1("""INSERT INTO scores (id, device_id, title, subtitle, game, data, listed)
                 VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
              (new_id(), d["id"], body.title, body.subtitle, body.game, body.data.model_dump_json(), body.listed))


@app.put("/api/scores/{sid}")
def update_score(sid: str, body: ScoreIn, d=Depends(require_device)):
    rate(f"score:{d['id']}", 120)
    r = q1("""UPDATE scores SET title = %s, subtitle = %s, game = %s, data = %s, listed = %s, updated_at = now()
              WHERE id = %s AND device_id = %s RETURNING id""",
           (body.title, body.subtitle, body.game, body.data.model_dump_json(), body.listed, sid, d["id"]))
    if not r:
        raise HTTPException(404, "missing")
    return r


@app.delete("/api/scores/{sid}")
def delete_score(sid: str, d=Depends(current_device), admin: bool = Depends(is_admin)):
    if not (d or admin):
        raise HTTPException(401, "device")
    r = q1("DELETE FROM scores WHERE id = %s AND (%s OR device_id = %s) RETURNING id", (sid, admin, d and d["id"]))
    if not r:
        raise HTTPException(404, "missing")
    q("DELETE FROM reports WHERE kind = 'score' AND target = %s", (sid,))
    return r


# ---------- likes ----------

def like_count(sid):
    return q1("SELECT count(*) AS likes FROM votes WHERE score_id = %s", (sid,))


@app.post("/api/scores/{sid}/like")
def like(sid: str, d=Depends(require_device)):
    rate(f"like:{d['id']}", 300)
    visible_score(sid, d, False)
    q("INSERT INTO votes (score_id, device_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (sid, d["id"]))
    return {**like_count(sid), "liked": True}


@app.delete("/api/scores/{sid}/like")
def unlike(sid: str, d=Depends(require_device)):
    q("DELETE FROM votes WHERE score_id = %s AND device_id = %s", (sid, d["id"]))
    return {**like_count(sid), "liked": False}


# ---------- comments ----------

class CommentIn(BaseModel):
    body: Text(1, 1000)


@app.get("/api/scores/{sid}/comments")
def list_comments(sid: str, d=Depends(current_device)):
    # shortcut: newest 200 only, add paging if threads get longer
    rows = q("""SELECT c.id, c.body, c.created_at, d.id AS author_id, d.name AS author_name
                FROM comments c JOIN devices d ON d.id = c.device_id
                WHERE c.score_id = %s AND NOT c.hidden AND NOT d.banned ORDER BY c.created_at DESC LIMIT 200""", (sid,))
    for r in rows:
        r["mine"] = bool(d) and r["author_id"] == d["id"]
    return rows[::-1]


@app.post("/api/scores/{sid}/comments")
def add_comment(sid: str, body: CommentIn, d=Depends(require_device)):
    rate(f"comment:{d['id']}", 30)
    visible_score(sid, d, False)
    r = q1("INSERT INTO comments (score_id, device_id, body) VALUES (%s, %s, %s) RETURNING id, body, created_at",
           (sid, d["id"], body.body))
    return {**r, "author_id": d["id"], "author_name": d["name"], "mine": True}


@app.delete("/api/comments/{cid}")
def delete_comment(cid: int, d=Depends(current_device), admin: bool = Depends(is_admin)):
    if not (d or admin):
        raise HTTPException(401, "device")
    r = q1("DELETE FROM comments WHERE id = %s AND (%s OR device_id = %s) RETURNING id", (cid, admin, d and d["id"]))
    if not r:
        raise HTTPException(404, "missing")
    q("DELETE FROM reports WHERE kind = 'comment' AND target = %s", (str(cid),))
    return r


# ---------- reports and moderation ----------

class ReportIn(BaseModel):
    kind: Literal["score", "comment"]
    target: Text(1, 40)
    reason: Text(0, 300) = ""


TABLE = {"score": "scores", "comment": "comments"}


@app.post("/api/reports")
def report(body: ReportIn, d=Depends(require_device)):
    rate(f"report:{d['id']}", 30)
    table = TABLE[body.kind]
    if body.kind == "comment" and not body.target.isdigit():
        raise HTTPException(404, "missing")
    if not q1(f"SELECT 1 FROM {table} WHERE id = %s", (body.target,)):
        raise HTTPException(404, "missing")
    q("INSERT INTO reports (kind, target, device_id, reason) VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
      (body.kind, body.target, d["id"], body.reason))
    n = q1("SELECT count(*) AS n FROM reports WHERE kind = %s AND target = %s", (body.kind, body.target))["n"]
    hidden = n >= REPORT_THRESHOLD
    if hidden:
        q(f"UPDATE {table} SET hidden = true WHERE id = %s", (body.target,))
    return {"ok": True, "hidden": hidden}


@app.get("/api/admin/reports", dependencies=[Depends(require_admin)])
def admin_reports():
    return q("""SELECT r.kind, r.target, count(*) AS reports, max(r.created_at) AS last,
                  string_agg(NULLIF(r.reason, ''), ' · ') AS reasons,
                  COALESCE(s.title, c.body) AS text, COALESCE(s.hidden, c.hidden) AS hidden,
                  COALESCE(s.id, c.score_id) AS score_id, a.id AS author_id, a.name AS author_name, a.banned AS author_banned
                FROM reports r
                LEFT JOIN scores s ON r.kind = 'score' AND s.id = r.target
                LEFT JOIN comments c ON r.kind = 'comment' AND c.id::text = r.target
                LEFT JOIN devices a ON a.id = COALESCE(s.device_id, c.device_id)
                GROUP BY r.kind, r.target, s.title, c.body, s.hidden, c.hidden, s.id, c.score_id, a.id
                ORDER BY hidden DESC, last DESC LIMIT 200""")


class TargetIn(BaseModel):
    kind: Literal["score", "comment"]
    target: Text(1, 40)


@app.post("/api/admin/restore", dependencies=[Depends(require_admin)])
def admin_restore(body: TargetIn):
    """Shows the content again and clears its reports, so hiding it again needs new reports."""
    if body.kind == "comment" and not body.target.isdigit():
        raise HTTPException(404, "missing")
    q(f"UPDATE {TABLE[body.kind]} SET hidden = false WHERE id = %s", (body.target,))
    q("DELETE FROM reports WHERE kind = %s AND target = %s", (body.kind, body.target))
    return {"ok": True}


class BanIn(BaseModel):
    device_id: Text(1, 40)
    banned: bool = True


@app.post("/api/admin/ban", dependencies=[Depends(require_admin)])
def admin_ban(body: BanIn):
    r = q1("UPDATE devices SET banned = %s WHERE id = %s RETURNING id, banned", (body.banned, body.device_id))
    if not r:
        raise HTTPException(404, "missing")
    return r


@app.get("/api/admin/check", dependencies=[Depends(require_admin)])
def admin_check():
    return {"ok": True}


# ---------- pages ----------

def with_meta(page: str, title: str, desc: str, url: str) -> str:
    s, e = (SITE / page).read_text("utf-8"), html.escape
    s = re.sub(r"<title>.*?</title>", lambda m: f"<title>{e(title)}</title>", s, count=1)
    for prop, val in (("og:title", title), ("og:description", desc), ("og:url", url)):
        s = re.sub(rf'(<meta property="{prop}" content=")[^"]*', lambda m: m.group(1) + e(val), s, count=1)
    return re.sub(r'(<link rel="canonical" href=")[^"]*', lambda m: m.group(1) + e(url), s, count=1)


@app.get("/s/{sid}", response_class=HTMLResponse)
def score_page(sid: str, request: Request):
    """The editor, with the sheet's title in the link preview of chat apps and social networks."""
    s = q1("SELECT title, subtitle, hidden FROM scores WHERE id = %s", (sid,))
    if not s or s["hidden"]:
        return HTMLResponse((SITE / "index.html").read_text("utf-8"))
    desc = (s["subtitle"] + " · " if s["subtitle"] else "") + "Ocarina of Time"
    return with_meta("index.html", s["title"], desc, str(request.url))


@app.get("/comunidad")
def community_page():
    return FileResponse(SITE / "comunidad.html")


SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "X-Frame-Options": "SAMEORIGIN",
}


@app.middleware("http")
async def headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.update(SECURITY_HEADERS)
    path = request.url.path
    if path.startswith(("/fonts/", "/vendor/")):
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


app.mount("/", StaticFiles(directory=SITE, html=True), name="site")
