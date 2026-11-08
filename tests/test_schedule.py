import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from homerhythm import db, schedule as S
from homerhythm.seed import seed

HOUSE = Path(__file__).resolve().parent.parent / "data" / "house.yaml"
MON = date(2026, 11, 16)   # a Monday
TUE = MON + timedelta(days=1)


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    seed(c, HOUSE)
    return c


def items_on(conn, d):
    return conn.execute(
        "SELECT i.*, t.name, t.room_id, t.robot, t.minutes, t.days FROM item i JOIN task t ON t.id=i.task_id "
        "WHERE i.date=?", (d.isoformat(),)).fetchall()


def test_seed_builds_themed_week(conn):
    themes = dict(conn.execute("SELECT dow, theme FROM day_theme").fetchall())
    assert themes["tue"] == "Bedrooms" and themes["fri"] == "Bathrooms"
    names = [r["name"] for r in conn.execute("SELECT name FROM task")]
    assert names.count("Bedroom refresh") == 6
    # half bath has no shower: no shower steps
    hb = conn.execute("SELECT steps FROM task WHERE room_id='half_bath'").fetchone()
    assert not any("shower" in s["name"].lower() for s in json.loads(hb["steps"]))
    # theatre isn't robot-reachable: gets a manual vacuum step, others say Roborock
    th = conn.execute("SELECT steps, note FROM task WHERE room_id='theatre'").fetchone()
    assert th["note"] is None


def test_weekday_vs_weekend_slots(conn):
    wd = [s.id for s in S.day_slots(conn, MON)]
    we = [s.id for s in S.day_slots(conn, MON + timedelta(days=5))]
    assert "after_truman_leaves" in wd and "after_truman_leaves" not in we
    assert "kids_activities" not in wd  # busy blocks come from the calendar later
    tl = {s.id: s for s in S.day_slots(conn, MON)}["after_truman_leaves"]
    assert tl.start.strftime("%H:%M") == "08:30"


def test_anchor_tap_shifts_following_slots(conn):
    before = {s.id: s.start for s in S.day_slots(conn, MON)}
    S.tap_anchor(conn, MON, "little_girls_wake", datetime.combine(MON, datetime.min.time()).replace(hour=9, minute=30))
    after = {s.id: s.start for s in S.day_slots(conn, MON)}
    assert after["little_girls_wake"].strftime("%H:%M") == "09:30"
    assert after["girls_settled"] - after["little_girls_wake"] == timedelta(minutes=120)
    assert after["lunchtime"] - before["lunchtime"] == timedelta(minutes=30)
    assert after["before_truman_wakes"] == before["before_truman_wakes"]


def test_generation_respects_capacity_and_rules(conn):
    S.ensure_week(conn, MON)
    for i in range(7):
        d = MON + timedelta(days=i)
        slots = {s.id: s for s in S.day_slots(conn, d)}
        for sid, s in slots.items():
            used = sum(r["minutes"] for r in items_on(conn, d) if r["slot_id"] == sid and not r["robot"])
            assert used <= s.minutes, (d, sid)
    # Gigi's room and the nursery are never planned into Gigi's nap
    for r in items_on(conn, TUE):
        if r["room_id"] in ("nursery", "georgia_room"):
            assert r["slot_id"] != "gigi_nap"
    # robot items have no slot
    assert all(r["slot_id"] is None for r in items_on(conn, MON) if r["robot"])
    # the week is only generated once
    n = conn.execute("SELECT COUNT(*) FROM item").fetchone()[0]
    S.ensure_week(conn, MON + timedelta(days=3))
    assert conn.execute("SELECT COUNT(*) FROM item").fetchone()[0] == n


def test_auto_slide_moves_missed_items_forward(conn):
    S.ensure_week(conn, MON)
    early = [r for r in items_on(conn, TUE) if r["slot_id"] == "before_truman_wakes"]
    assert early
    now = datetime.combine(TUE, datetime.min.time()).replace(hour=10)
    moved = S.auto_slide(conn, now)
    assert moved >= len(early)
    for r in early:
        it = conn.execute("SELECT * FROM item WHERE id=?", (r["id"],)).fetchone()
        assert it["moved_count"] >= 1
        if it["date"] and it["slot_id"]:
            s = {x.id: x for x in S.day_slots(conn, date.fromisoformat(it["date"]))}[it["slot_id"]]
            assert s.end > now


def test_daily_items_lapse_instead_of_piling_up(conn):
    S.ensure_week(conn, MON)
    S.auto_slide(conn, datetime.combine(TUE, datetime.min.time()).replace(hour=6))
    mon_daily = [r for r in items_on(conn, MON) if "daily" in json.loads(r["days"]) and not r["robot"]]
    assert mon_daily and all(
        conn.execute("SELECT status FROM item WHERE id=?", (r["id"],)).fetchone()[0] == "lapsed" for r in mon_daily)


def test_done_logs_last_done_and_house_steps(conn):
    S.ensure_week(conn, MON)
    now = datetime.combine(MON, datetime.min.time()).replace(hour=9)
    beds = next(r for r in items_on(conn, MON) if r["name"] == "Make all beds")
    S.toggle_step(conn, beds["id"], 0, now)
    first_room = json.loads(conn.execute("SELECT steps FROM task WHERE id=?", (beds["task_id"],)).fetchone()[0])[0]["room"]
    assert S.last_done(conn, beds["task_id"], first_room) is not None
    S.set_done(conn, beds["id"], True, now)
    assert conn.execute("SELECT COUNT(*) FROM completion WHERE item_id=?", (beds["id"],)).fetchone()[0] == 6
    S.set_done(conn, beds["id"], False, now)
    assert conn.execute("SELECT COUNT(*) FROM completion WHERE item_id=?", (beds["id"],)).fetchone()[0] == 0
    assert S.ago((now - timedelta(days=4)).isoformat(), now) == "4 days ago"


def test_close_slot_moves_items_and_skip(conn):
    S.ensure_week(conn, MON)
    now = datetime.combine(TUE, datetime.min.time()).replace(hour=12, minute=50)
    nap = [r for r in items_on(conn, TUE) if r["slot_id"] == "gigi_nap"]
    assert nap
    S.close_slot(conn, TUE, "gigi_nap", now)
    assert not [r for r in items_on(conn, TUE) if r["slot_id"] == "gigi_nap" and r["status"] == "planned"]
    S.set_skipped(conn, nap[0]["id"], True)
    assert conn.execute("SELECT status FROM item WHERE id=?", (nap[0]["id"],)).fetchone()[0] == "skipped"


def test_rebuild_keeps_done_items(conn):
    S.ensure_week(conn, MON)
    now = datetime.combine(TUE, datetime.min.time()).replace(hour=9)
    it = items_on(conn, TUE)[0]
    S.set_done(conn, it["id"], True, now)
    S.rebuild_rest_of_week(conn, TUE)
    assert conn.execute("SELECT status FROM item WHERE id=?", (it["id"],)).fetchone()[0] == "done"
    dup = conn.execute("SELECT COUNT(*) FROM item WHERE task_id=? AND orig_date=?",
                       (it["task_id"], TUE.isoformat())).fetchone()[0]
    assert dup == 1


def test_first_open_midweek_skips_past_days(conn):
    S.ensure_week(conn, MON + timedelta(days=2))
    assert conn.execute("SELECT COUNT(*) FROM item WHERE orig_date < ?", ((MON + timedelta(days=2)).isoformat(),)).fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM item").fetchone()[0] > 0
