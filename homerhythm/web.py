"""Web UI (FastAPI + Jinja + htmx boost). Every POST redirects back, so it works without JS too."""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import db, schedule as S
from .seed import seed

HERE = Path(__file__).resolve().parent
TZ = ZoneInfo(os.environ.get("HOMERHYTHM_TZ", "America/Chicago"))
DOW_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def now() -> datetime:
    """Local wall-clock time. HOMERHYTHM_NOW=2026-11-17T13:20 pins it for testing."""
    fake = os.environ.get("HOMERHYTHM_NOW")
    if fake:
        return datetime.fromisoformat(fake)
    return datetime.now(TZ).replace(tzinfo=None, second=0, microsecond=0)


def create_app(conn=None) -> FastAPI:
    conn = conn or db.connect()
    if not db.is_seeded(conn):
        seed(conn, db.HOUSE_YAML)

    app = FastAPI(title="Home Rhythm")
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    tpl = Jinja2Templates(directory=HERE / "templates")
    tpl.env.globals["fmt_time"] = S.fmt_time

    def back(request: Request, fallback: str = "/") -> RedirectResponse:
        return RedirectResponse(request.headers.get("referer") or fallback, status_code=303)

    def refresh() -> datetime:
        n = now()
        S.ensure_week(conn, n.date())
        S.auto_slide(conn, n)
        conn.commit()
        return n

    rooms = lambda: {r["id"]: r for r in conn.execute("SELECT * FROM room ORDER BY sort")}  # noqa: E731

    def item_view(row, n: datetime) -> dict:
        task = conn.execute("SELECT * FROM task WHERE id=?", (row["task_id"],)).fetchone()
        rm = rooms()
        steps = json.loads(task["steps"])
        done_idx = set(json.loads(row["steps_done"]))
        step_views = []
        for i, st in enumerate(steps):
            v = {"i": i, "name": st["name"], "done": i in done_idx}
            if st.get("room"):
                v["ago"] = S.ago(S.last_done(conn, task["id"], st["room"], exclude_item=row["id"]), n)
            step_views.append(v)
        return {
            "id": row["id"], "name": task["name"], "room": rm[task["room_id"]]["name"] if task["room_id"] in rm else None,
            "minutes": task["minutes"], "status": row["status"], "robot": task["robot"], "note": task["note"],
            "scope": task["scope"], "steps": step_views, "steps_done": len(done_idx),
            "moved": row["moved_count"], "group": task["group_label"],
            "ago": S.ago(S.last_done(conn, task["id"], None if task["scope"] == "house" else task["room_id"],
                                     exclude_item=row["id"]), n),
            "daily": "daily" in json.loads(task["days"]),
        }

    def move_targets(n: datetime) -> list[dict]:
        monday = S.monday_of(n.date())
        out = []
        for i in range(7):
            d = monday + timedelta(days=i)
            if d < n.date():
                continue
            opts = [{"value": f"{d.isoformat()}|{s.id}", "label": f"{s.name} ({S.fmt_time(s.start)})"}
                    for s in S.day_slots(conn, d) if not s.closed and (d > n.date() or s.end > n)]
            opts.append({"value": f"{d.isoformat()}|", "label": "Anytime"})
            out.append({"day": DOW_NAMES[d.weekday()] + ("" if d != n.date() else " (today)"), "opts": opts})
        return out

    def day_context(d: date, n: datetime) -> dict:
        slots = S.day_slots(conn, d)
        items = conn.execute(
            "SELECT i.* FROM item i JOIN task t ON t.id=i.task_id WHERE i.date=? AND i.status!='lapsed' ORDER BY t.sort",
            (d.isoformat(),)).fetchall()
        by_slot: dict = {}
        anytime, robot = [], []
        for r in items:
            v = item_view(r, n)
            if v["robot"]:
                robot.append(v)
            elif r["slot_id"] and any(s.id == r["slot_id"] for s in slots):
                by_slot.setdefault(r["slot_id"], []).append(v)
            else:
                anytime.append(v)
        slot_views = []
        for s in slots:
            its = by_slot.get(s.id, [])
            used = sum(i["minutes"] for i in its if i["status"] in ("planned", "done"))
            state = "past" if d < n.date() or (d == n.date() and s.end <= n) else \
                    "now" if d == n.date() and s.start <= n < s.end else "later"
            slot_views.append({"s": s, "its": its, "used": used, "state": state,
                               "left": sum(1 for i in its if i["status"] == "planned")})
        theme = conn.execute("SELECT theme FROM day_theme WHERE dow=?", (S.DOW[d.weekday()],)).fetchone()
        total = [i for sv in slot_views for i in sv["its"]] + anytime
        anchors_row = [s for s in slots if s.anchor]
        evening = next((s for s in slots if s.id == "after_little_girls_sleep"), None)
        show_summary = d == n.date() and evening is not None and (evening.anchored or n >= evening.start)
        return {
            "d": d, "day_name": DOW_NAMES[d.weekday()], "theme": theme["theme"] if theme else "",
            "slots": slot_views, "anytime": anytime, "robot": robot, "is_today": d == n.date(),
            "done_count": sum(1 for i in total if i["status"] == "done"),
            "total_count": sum(1 for i in total if i["status"] != "skipped"),
            "anchors": anchors_row,
            "summary": S.summary(conn, d, n) if show_summary else None,
            "prev": d - timedelta(days=1), "next": d + timedelta(days=1),
        }

    def tray_count(n: datetime) -> int:
        return conn.execute("SELECT COUNT(*) FROM item WHERE week_start=? AND date IS NULL AND status='planned'",
                            (S.monday_of(n.date()).isoformat(),)).fetchone()[0]

    # ── pages ────────────────────────────────────────────────────────────────

    @app.get("/")
    async def today(request: Request):
        n = refresh()
        return tpl.TemplateResponse(request, "day.html", {
            **day_context(n.date(), n), "now": n, "targets": move_targets(n), "tray": tray_count(n), "page": "today"})

    @app.get("/day/{ds}")
    async def day(request: Request, ds: str):
        n = refresh()
        d = date.fromisoformat(ds)
        if d == n.date():
            return RedirectResponse("/", status_code=303)
        return tpl.TemplateResponse(request, "day.html", {
            **day_context(d, n), "now": n, "targets": move_targets(n), "tray": tray_count(n), "page": "day"})

    @app.get("/week")
    async def week(request: Request):
        n = refresh()
        monday = S.monday_of(n.date())
        days = [day_context(monday + timedelta(days=i), n) for i in range(7)]
        tray = [item_view(r, n) for r in conn.execute(
            "SELECT i.* FROM item i JOIN task t ON t.id=i.task_id WHERE i.week_start=? AND i.date IS NULL "
            "AND i.status='planned' ORDER BY t.sort", (monday.isoformat(),))]
        return tpl.TemplateResponse(request, "week.html", {
            "days": days, "tray_items": tray, "now": n, "targets": move_targets(n), "tray": len(tray),
            "page": "week", "monday": monday})

    @app.get("/summary")
    async def summary_page(request: Request):
        n = refresh()
        return tpl.TemplateResponse(request, "summary.html", {
            "sm": S.summary(conn, n.date(), n), "now": n, "tray": tray_count(n), "page": "summary"})

    # ── item actions ─────────────────────────────────────────────────────────

    @app.post("/item/{item_id}/toggle")
    async def toggle(request: Request, item_id: int):
        n = now()
        st = conn.execute("SELECT status FROM item WHERE id=?", (item_id,)).fetchone()["status"]
        S.set_done(conn, item_id, st != "done", n)
        conn.commit()
        return back(request)

    @app.post("/item/{item_id}/step/{idx}")
    async def step(request: Request, item_id: int, idx: int):
        S.toggle_step(conn, item_id, idx, now())
        conn.commit()
        return back(request)

    @app.post("/item/{item_id}/move")
    async def move(request: Request, item_id: int, to: str = Form(...)):
        n = now()
        if to == "next":
            S.move_next(conn, item_id, n)
        elif to == "tomorrow":
            S.move_tomorrow(conn, item_id, n)
        elif to == "tray":
            S.move_item(conn, item_id, None, None, "manual", n)
        elif to == "skip":
            S.set_skipped(conn, item_id, True)
        elif to == "unskip":
            S.set_skipped(conn, item_id, False)
        elif "|" in to:
            ds, sid = to.split("|", 1)
            S.move_item(conn, item_id, date.fromisoformat(ds), sid or None, "manual", n)
        conn.commit()
        return back(request)

    # ── slot actions (today) ─────────────────────────────────────────────────

    @app.post("/anchor/{slot_id}")
    async def anchor(request: Request, slot_id: str, clear: str = Form("")):
        n = now()
        if clear:
            S.clear_anchor(conn, n.date(), slot_id)
        else:
            S.tap_anchor(conn, n.date(), slot_id, n)
        conn.commit()
        return back(request)

    @app.post("/slot/{ds}/{slot_id}/close")
    async def close(request: Request, ds: str, slot_id: str, reopen: str = Form("")):
        d = date.fromisoformat(ds)
        if reopen:
            S.reopen_slot(conn, d, slot_id)
        else:
            S.close_slot(conn, d, slot_id, now())
        conn.commit()
        return back(request)

    # ── settings ─────────────────────────────────────────────────────────────

    @app.get("/settings")
    async def settings(request: Request):
        n = refresh()
        slots = conn.execute("SELECT * FROM slot WHERE busy=0 ORDER BY ord").fetchall()
        tasks = conn.execute("SELECT t.*, r.name AS room_name FROM task t LEFT JOIN room r ON r.id=t.room_id "
                             "ORDER BY t.sort").fetchall()
        groups = []
        for key, label in [("daily", "Daily")] + [(S.DOW[i], DOW_NAMES[i]) for i in range(7)]:
            ts = [t for t in tasks if key in json.loads(t["days"])]
            theme = conn.execute("SELECT theme FROM day_theme WHERE dow=?", (key,)).fetchone()
            if ts:
                groups.append({"label": label, "theme": theme["theme"] if theme else "", "tasks": ts})
        return tpl.TemplateResponse(request, "settings.html", {
            "slots": slots, "groups": groups, "now": n, "tray": tray_count(n), "page": "settings"})

    @app.post("/settings/slots")
    async def save_slots(request: Request):
        form = await request.form()
        for s in conn.execute("SELECT id FROM slot").fetchall():
            sid = s["id"]
            if f"{sid}__present" not in form:
                continue
            vals = {}
            for p in ("wd", "we"):
                vals[f"{p}_on"] = 1 if form.get(f"{sid}__{p}_on") else 0
                vals[f"{p}_start"] = form.get(f"{sid}__{p}_start") or None
                m = form.get(f"{sid}__{p}_minutes")
                vals[f"{p}_minutes"] = int(m) if m else None
            conn.execute(
                "UPDATE slot SET wd_on=:wd_on, wd_start=:wd_start, wd_minutes=:wd_minutes, "
                "we_on=:we_on, we_start=:we_start, we_minutes=:we_minutes WHERE id=:id", {**vals, "id": sid})
        conn.commit()
        return RedirectResponse("/settings?saved=slots", status_code=303)

    @app.post("/week/rebuild")
    async def rebuild(request: Request):
        S.rebuild_rest_of_week(conn, now().date())
        conn.commit()
        return RedirectResponse("/", status_code=303)

    def task_form_ctx(request, task, n):
        return tpl.TemplateResponse(request, "task.html", {
            "t": task, "rooms": list(rooms().values()),
            "slots": conn.execute("SELECT * FROM slot WHERE busy=0 ORDER BY ord").fetchall(),
            "dows": list(zip(S.DOW, DOW_NAMES)),
            "days": json.loads(task["days"]) if task else [],
            "prefs": json.loads(task["preferred_slots"]) if task else [],
            "steps_text": "\n".join(s["name"] for s in json.loads(task["steps"])) if task else "",
            "now": n, "tray": tray_count(n), "page": "settings"})

    @app.get("/task/new")
    async def new_task(request: Request):
        return task_form_ctx(request, None, refresh())

    @app.get("/task/{task_id}")
    async def edit_task(request: Request, task_id: int):
        t = conn.execute("SELECT * FROM task WHERE id=?", (task_id,)).fetchone()
        return task_form_ctx(request, t, refresh())

    @app.post("/task/save")
    async def save_task(request: Request):
        f = await request.form()
        tid = f.get("id")
        days = f.getlist("days")
        if "daily" in days:
            days = ["daily"]
        prefs = f.getlist("prefs")
        room_id = f.get("room_id") or None
        old = conn.execute("SELECT * FROM task WHERE id=?", (tid,)).fetchone() if tid else None
        old_steps = json.loads(old["steps"]) if old else []
        by_name = {s["name"]: s for s in old_steps}
        steps = [by_name.get(line.strip(), {"name": line.strip()})
                 for line in (f.get("steps") or "").splitlines() if line.strip()]
        scope = "house" if any(s.get("room") for s in steps) else ("room" if room_id else "none")
        vals = (f.get("name", "").strip() or "Untitled", room_id, scope, json.dumps(steps),
                int(f.get("minutes") or 0), json.dumps(days), json.dumps(prefs),
                1 if f.get("robot") else 0, 1 if f.get("active") else 0)
        if old:
            conn.execute("UPDATE task SET name=?, room_id=?, scope=?, steps=?, minutes=?, days=?, preferred_slots=?, "
                         "robot=?, active=? WHERE id=?", (*vals, tid))
        else:
            sort = conn.execute("SELECT COALESCE(MAX(sort),0)+1 FROM task").fetchone()[0]
            conn.execute("INSERT INTO task(name, room_id, scope, steps, minutes, days, preferred_slots, robot, active, "
                         "group_label, sort) VALUES (?,?,?,?,?,?,?,?,?,?,?)", (*vals, "Custom", sort))
        conn.commit()
        return RedirectResponse("/settings?saved=task", status_code=303)

    @app.get("/manifest.webmanifest")
    async def manifest():
        from fastapi.responses import JSONResponse
        return JSONResponse({
            "name": "Home Rhythm", "short_name": "Rhythm", "start_url": "/", "display": "standalone",
            "background_color": "#f7f4ef", "theme_color": "#5b7f6a",
            "icons": [{"src": "/static/icon.svg", "sizes": "any", "type": "image/svg+xml"}],
        }, media_type="application/manifest+json")

    app.state.conn = conn
    return app
