"""Scheduling: slot times for a day, weekly plan generation, auto-slide, moves, and the daily summary."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

DOW = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
SCHOOL_START, SCHOOL_END = time(8, 30), time(14, 30)


@dataclass
class SlotInst:
    id: str
    name: str
    start: datetime
    end: datetime
    minutes: int
    anchor: str | None
    anchored: bool
    closed: bool
    category: str | None

    def label(self) -> str:
        return f"{fmt_time(self.start)}–{fmt_time(self.end)}"


def fmt_time(dt: datetime) -> str:
    h = dt.hour % 12 or 12
    return f"{h}:{dt.minute:02d}{'am' if dt.hour < 12 else 'pm'}"


def monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _hm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


# ── day state ────────────────────────────────────────────────────────────────

def get_day_state(conn, d: date) -> tuple[dict, list]:
    r = conn.execute("SELECT anchors, closed FROM day_state WHERE date=?", (d.isoformat(),)).fetchone()
    return (json.loads(r["anchors"]), json.loads(r["closed"])) if r else ({}, [])


def set_day_state(conn, d: date, anchors: dict, closed: list) -> None:
    conn.execute(
        "INSERT INTO day_state(date, anchors, closed) VALUES (?,?,?) "
        "ON CONFLICT(date) DO UPDATE SET anchors=excluded.anchors, closed=excluded.closed",
        (d.isoformat(), json.dumps(anchors), json.dumps(closed)),
    )


def day_slots(conn, d: date) -> list[SlotInst]:
    """Slots for a date, using the weekday/weekend schedule and any anchor taps.

    A tapped anchor sets that slot's start; the shift carries to the slots after it
    until the next tapped anchor. Offset slots follow their reference slot.
    """
    anchors, closed = get_day_state(conn, d)
    p = "we" if d.weekday() >= 5 else "wd"
    out, actual, delta = [], {}, timedelta(0)
    for s in conn.execute("SELECT * FROM slot ORDER BY ord"):
        if s["busy"] or not s[f"{p}_on"]:
            continue
        minutes = s[f"{p}_minutes"] or 0
        tapped = s["id"] in anchors
        if s["offset_from"]:
            ref = actual.get(s["offset_from"])
            if ref is None:
                continue
            start = ref + timedelta(minutes=s["offset_minutes"] or 0)
        else:
            if not s[f"{p}_start"]:
                continue
            base = datetime.combine(d, _hm(s[f"{p}_start"]))
            if tapped:
                start = datetime.combine(d, _hm(anchors[s["id"]]))
                delta = start - base
            else:
                start = base + delta
        actual[s["id"]] = start
        out.append(SlotInst(s["id"], s["name"], start, start + timedelta(minutes=minutes), minutes,
                            s["anchor"], tapped, s["id"] in closed, s["category"]))
    out.sort(key=lambda x: x.start)
    return out


# ── placement ────────────────────────────────────────────────────────────────

def _rooms(conn) -> dict:
    return {r["id"]: r for r in conn.execute("SELECT * FROM room")}


def _used(conn, d: date, slot_id: str, exclude_item: int | None = None) -> int:
    return conn.execute(
        """SELECT COALESCE(SUM(t.minutes),0) FROM item i JOIN task t ON t.id=i.task_id
           WHERE i.date=? AND i.slot_id=? AND i.status IN ('planned','done') AND t.robot=0
           AND i.id != COALESCE(?, -1)""",
        (d.isoformat(), slot_id, exclude_item),
    ).fetchone()[0]


def allowed(task, room, slot: SlotInst) -> bool:
    if slot.closed:
        return False
    if slot.category == "meals" and task["category"] != "meals":
        return False
    if room is not None and slot.id in json.loads(room["never_during"] or "[]"):
        return False
    return True


def find_fit(conn, task, room, d: date, after: datetime | None = None, use_prefs: bool = False,
             exclude_item: int | None = None) -> str | None:
    """First slot on date `d` (ending after `after`) that allows the task and has room for it."""
    slots = [s for s in day_slots(conn, d) if after is None or s.end > after]
    if use_prefs:
        prefs = json.loads(task["preferred_slots"] or "[]")

        def key(s):
            school = 0
            if room is not None and room["prefer_when"] == "kids_at_school" and d.weekday() < 5:
                school = 0 if SCHOOL_START <= s.start.time() < SCHOOL_END else 1
            return (0 if s.id in prefs else 1, school, s.start)

        slots.sort(key=key)
    for s in slots:
        if not allowed(task, room, s):
            continue
        cap = s.minutes - _used(conn, d, s.id, exclude_item)
        if after is not None and s.start < after:
            cap = min(cap, int((s.end - after).total_seconds() // 60))
        if cap >= task["minutes"]:
            return s.id
    return None


def _tasks_for(conn, d: date):
    dow = DOW[d.weekday()]
    rows = conn.execute("SELECT * FROM task WHERE active=1 ORDER BY sort").fetchall()
    out = [t for t in rows if dow in json.loads(t["days"]) or "daily" in json.loads(t["days"])]

    def key(t):
        return (0 if json.loads(t["preferred_slots"]) else 1,
                0 if "daily" in json.loads(t["days"]) else 1,
                -t["minutes"])

    return sorted(out, key=key)


def plan_days(conn, monday: date, dates: list[date]) -> None:
    rooms = _rooms(conn)
    for d in dates:
        for t in _tasks_for(conn, d):
            exists = conn.execute(
                "SELECT 1 FROM item WHERE task_id=? AND week_start=? AND orig_date=?",
                (t["id"], monday.isoformat(), d.isoformat()),
            ).fetchone()
            if exists:
                continue
            slot_id = None
            if not t["robot"]:
                slot_id = find_fit(conn, t, rooms.get(t["room_id"]), d, use_prefs=True)
            conn.execute(
                "INSERT INTO item(week_start, task_id, date, slot_id, orig_date, orig_slot) VALUES (?,?,?,?,?,?)",
                (monday.isoformat(), t["id"], d.isoformat(), slot_id, d.isoformat(), slot_id),
            )


def ensure_week(conn, today: date) -> date:
    """Monday fresh start: build the week from the baseline the first time it's opened."""
    monday = monday_of(today)
    if not conn.execute("SELECT 1 FROM week WHERE start=?", (monday.isoformat(),)).fetchone():
        conn.execute("INSERT INTO week(start, generated_at) VALUES (?, ?)",
                     (monday.isoformat(), datetime.now().isoformat(timespec="seconds")))
        # First open mid-week (e.g. launch day): don't create items for days already gone.
        plan_days(conn, monday, [monday + timedelta(days=i) for i in range(7)
                                 if monday + timedelta(days=i) >= today])
    return monday


def rebuild_rest_of_week(conn, today: date) -> None:
    """Re-plan today..Sunday from the current baseline (after editing tasks or slots).
    Keeps done/skipped items and anything that already slid in from earlier days."""
    monday = ensure_week(conn, today)
    conn.execute(
        "DELETE FROM item WHERE week_start=? AND status='planned' AND orig_date>=?",
        (monday.isoformat(), today.isoformat()),
    )
    plan_days(conn, monday, [today + timedelta(days=i) for i in range((monday + timedelta(days=6) - today).days + 1)])


# ── moves ────────────────────────────────────────────────────────────────────

def _item(conn, item_id: int):
    return conn.execute(
        "SELECT i.*, t.minutes, t.robot, t.days, t.room_id, t.category, t.preferred_slots, t.name "
        "FROM item i JOIN task t ON t.id=i.task_id WHERE i.id=?", (item_id,)
    ).fetchone()


def move_item(conn, item_id: int, to_date: date | None, to_slot: str | None, reason: str, now: datetime) -> None:
    it = _item(conn, item_id)
    conn.execute(
        "INSERT INTO move(item_id, at, from_date, from_slot, to_date, to_slot, reason) VALUES (?,?,?,?,?,?,?)",
        (item_id, now.isoformat(timespec="seconds"), it["date"], it["slot_id"],
         to_date.isoformat() if to_date else None, to_slot, reason),
    )
    conn.execute("UPDATE item SET date=?, slot_id=?, moved_count=moved_count+1 WHERE id=?",
                 (to_date.isoformat() if to_date else None, to_slot, item_id))


def next_fit(conn, it, now: datetime, start_date: date, after: datetime | None, same_day_only: bool):
    """Search forward from start_date to Sunday for the first slot that fits."""
    rooms = _rooms(conn)
    sunday = monday_of(now.date()) + timedelta(days=6)
    d = start_date
    while d <= sunday:
        a = after if d == start_date else None
        if d == now.date():
            a = max(a, now) if a else now
        if d >= now.date():
            sid = find_fit(conn, it, rooms.get(it["room_id"]), d, after=a, exclude_item=it["id"])
            if sid:
                return d, sid
        if same_day_only:
            break
        d += timedelta(days=1)
    return None


def is_daily(it) -> bool:
    return "daily" in json.loads(it["days"])


def auto_slide(conn, now: datetime) -> int:
    """Move unfinished items whose slot has ended to the next slot that fits.
    Daily tasks only slide within their own day. Returns the number moved."""
    today = now.date()
    monday = monday_of(today)
    rows = conn.execute(
        """SELECT i.id, i.date, i.slot_id FROM item i JOIN task t ON t.id=i.task_id
           WHERE i.week_start=? AND i.status='planned' AND t.robot=0 AND i.date IS NOT NULL AND i.date<=?
           ORDER BY i.date, i.id""",
        (monday.isoformat(), today.isoformat()),
    ).fetchall()
    slot_cache: dict[str, dict] = {}
    moved = 0
    for r in rows:
        d = date.fromisoformat(r["date"])
        if d == today:
            if r["slot_id"] is None:
                continue
            if r["date"] not in slot_cache:
                slot_cache[r["date"]] = {s.id: s for s in day_slots(conn, d)}
            s = slot_cache[r["date"]].get(r["slot_id"])
            if s is not None and s.end > now and not s.closed:
                continue
        it = _item(conn, r["id"])
        if is_daily(it):
            if d < today:
                conn.execute("UPDATE item SET status='lapsed' WHERE id=?", (it["id"],))
                continue
            target = next_fit(conn, it, now, today, None, same_day_only=True)
            move_item(conn, it["id"], today, target[1] if target else None, "auto", now)
        else:
            target = next_fit(conn, it, now, today, None, same_day_only=False)
            if target:
                move_item(conn, it["id"], target[0], target[1], "auto", now)
            else:
                move_item(conn, it["id"], None, None, "auto", now)  # → "whenever" tray
        moved += 1
        slot_cache.clear()
    return moved


def move_next(conn, item_id: int, now: datetime, reason: str = "manual") -> None:
    it = _item(conn, item_id)
    start = date.fromisoformat(it["date"]) if it["date"] else now.date()
    start = max(start, now.date())
    after = None
    if it["date"] and it["slot_id"] and date.fromisoformat(it["date"]) == start:
        s = {x.id: x for x in day_slots(conn, start)}.get(it["slot_id"])
        after = s.end if s else None
    target = next_fit(conn, it, now, start, after, same_day_only=is_daily(it))
    if target:
        move_item(conn, item_id, target[0], target[1], reason, now)
    elif is_daily(it):
        move_item(conn, item_id, start, None, reason, now)
    else:
        move_item(conn, item_id, None, None, reason, now)


def move_tomorrow(conn, item_id: int, now: datetime) -> None:
    it = _item(conn, item_id)
    tomorrow = now.date() + timedelta(days=1)
    if tomorrow > monday_of(now.date()) + timedelta(days=6):
        move_item(conn, item_id, None, None, "manual", now)
        return
    sid = find_fit(conn, it, _rooms(conn).get(it["room_id"]), tomorrow, exclude_item=item_id)
    move_item(conn, item_id, tomorrow, sid, "manual", now)


def close_slot(conn, d: date, slot_id: str, now: datetime) -> None:
    anchors, closed = get_day_state(conn, d)
    if slot_id not in closed:
        closed.append(slot_id)
    set_day_state(conn, d, anchors, closed)
    for r in conn.execute("SELECT id FROM item WHERE date=? AND slot_id=? AND status='planned'",
                          (d.isoformat(), slot_id)).fetchall():
        move_next(conn, r["id"], now, reason="closed")


def reopen_slot(conn, d: date, slot_id: str) -> None:
    anchors, closed = get_day_state(conn, d)
    set_day_state(conn, d, anchors, [c for c in closed if c != slot_id])


def tap_anchor(conn, d: date, slot_id: str, at: datetime) -> None:
    anchors, closed = get_day_state(conn, d)
    anchors[slot_id] = at.strftime("%H:%M")
    set_day_state(conn, d, anchors, closed)


def clear_anchor(conn, d: date, slot_id: str) -> None:
    anchors, closed = get_day_state(conn, d)
    anchors.pop(slot_id, None)
    set_day_state(conn, d, anchors, closed)


# ── completion ───────────────────────────────────────────────────────────────

def _log(conn, it, room_id, now):
    conn.execute("INSERT INTO completion(item_id, task_id, room_id, done_at) VALUES (?,?,?,?)",
                 (it["id"], it["task_id"], room_id, now.isoformat(timespec="seconds")))


def set_done(conn, item_id: int, done: bool, now: datetime) -> None:
    it = _item(conn, item_id)
    task = conn.execute("SELECT * FROM task WHERE id=?", (it["task_id"],)).fetchone()
    steps = json.loads(task["steps"])
    if done:
        conn.execute("UPDATE item SET status='done', done_at=? WHERE id=?", (now.isoformat(timespec="seconds"), item_id))
        if task["scope"] == "house":
            logged = {r["room_id"] for r in conn.execute("SELECT room_id FROM completion WHERE item_id=?", (item_id,))}
            for st in steps:
                if st.get("room") and st["room"] not in logged:
                    _log(conn, it, st["room"], now)
            conn.execute("UPDATE item SET steps_done=? WHERE id=?", (json.dumps(list(range(len(steps)))), item_id))
        else:
            _log(conn, it, task["room_id"], now)
    else:
        conn.execute("UPDATE item SET status='planned', done_at=NULL WHERE id=?", (item_id,))
        conn.execute("DELETE FROM completion WHERE item_id=?", (item_id,))
        conn.execute("UPDATE item SET steps_done='[]' WHERE id=?", (item_id,))


def toggle_step(conn, item_id: int, idx: int, now: datetime) -> None:
    it = _item(conn, item_id)
    task = conn.execute("SELECT * FROM task WHERE id=?", (it["task_id"],)).fetchone()
    steps = json.loads(task["steps"])
    done = set(json.loads(it["steps_done"]))
    if idx in done:
        done.discard(idx)
        room = steps[idx].get("room")
        if room:
            conn.execute("DELETE FROM completion WHERE item_id=? AND room_id=?", (item_id, room))
        if it["status"] == "done":
            conn.execute("UPDATE item SET status='planned', done_at=NULL WHERE id=?", (item_id,))
            if task["scope"] != "house":
                conn.execute("DELETE FROM completion WHERE item_id=?", (item_id,))
    else:
        done.add(idx)
        if steps[idx].get("room"):
            _log(conn, it, steps[idx]["room"], now)
    conn.execute("UPDATE item SET steps_done=? WHERE id=?", (json.dumps(sorted(done)), item_id))
    if steps and len(done) >= len(steps) and it["status"] != "done":
        conn.execute("UPDATE item SET status='done', done_at=? WHERE id=?", (now.isoformat(timespec="seconds"), item_id))
        if task["scope"] != "house":
            _log(conn, it, task["room_id"], now)


def set_skipped(conn, item_id: int, skipped: bool) -> None:
    conn.execute("UPDATE item SET status=? WHERE id=?", ("skipped" if skipped else "planned", item_id))


def last_done(conn, task_id: int, room_id: str | None = None, exclude_item: int | None = None) -> str | None:
    q = "SELECT MAX(done_at) FROM completion WHERE task_id=? AND item_id != COALESCE(?, -1)"
    args: list = [task_id, exclude_item]
    if room_id:
        q += " AND room_id=?"
        args.append(room_id)
    return conn.execute(q, args).fetchone()[0]


def ago(ts: str | None, now: datetime) -> str:
    if not ts:
        return "not tracked yet"
    days = (now.date() - datetime.fromisoformat(ts).date()).days
    return "today" if days <= 0 else "yesterday" if days == 1 else f"{days} days ago"


# ── daily summary ────────────────────────────────────────────────────────────

def summary(conn, d: date, now: datetime) -> dict:
    ds = d.isoformat()
    done = conn.execute("SELECT COUNT(*) FROM item WHERE status='done' AND substr(done_at,1,10)=?", (ds,)).fetchone()[0]
    moved = conn.execute("SELECT COUNT(DISTINCT item_id) FROM move WHERE substr(at,1,10)=?", (ds,)).fetchone()[0]
    rooms = [r[0] for r in conn.execute(
        "SELECT DISTINCT r.name FROM completion c JOIN room r ON r.id=c.room_id WHERE substr(c.done_at,1,10)=? ORDER BY r.sort",
        (ds,))]
    monday = monday_of(d)
    tip = None
    r = conn.execute(
        """SELECT t.name, r.name AS room, i.moved_count FROM item i JOIN task t ON t.id=i.task_id
           LEFT JOIN room r ON r.id=t.room_id
           WHERE i.week_start=? AND i.status='planned' ORDER BY i.moved_count DESC LIMIT 1""",
        (monday.isoformat(),)).fetchone()
    if r and r["moved_count"] >= 3:
        what = r["name"] + (f" ({r['room']})" if r["room"] else "")
        tip = f"“{what}” has moved {r['moved_count']} times this week. Want to skip it this week, or give it a different slot?"
    if tip is None:
        tray = conn.execute("SELECT COUNT(*) FROM item WHERE week_start=? AND date IS NULL AND status='planned'",
                            (monday.isoformat(),)).fetchone()[0]
        if tray:
            tip = f"{tray} item{'s' if tray != 1 else ''} in the Whenever tray. Skipping a few this week is fine."
    tomorrow = d + timedelta(days=1)
    first = day_slots(conn, tomorrow)
    nxt = f"Tomorrow starts with {first[0].name} at {fmt_time(first[0].start)}." if first else None
    return {"done": done, "moved": moved, "rooms": rooms, "tip": tip, "tomorrow": nxt}
