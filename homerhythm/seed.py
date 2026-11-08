"""Load data/house.yaml into the database (first run, or `python -m homerhythm seed --reset`)."""
import json
from pathlib import Path

import yaml

DOW = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
LAUNDRY_STEPS = ["Start load", "Move to dryer", "Fold & put away"]


def _steps_for_routine(routines: dict, key: str, room: dict | None) -> tuple[list[dict], int, bool]:
    """Expand a routine into checklist steps. Returns (steps, minutes, has_robot_step)."""
    steps, minutes, robot = [], 0, False
    for st in routines[key]["steps"]:
        if "ref" in st:
            sub, m, r = _steps_for_routine(routines, st["ref"], room)
            steps += sub
            minutes += m
            robot = robot or r
            continue
        cond = st.get("only_if", "")
        if cond == "room.shower" and room is not None and room.get("shower") is False:
            continue
        if st.get("robot"):
            robot = True
            continue
        name = st["name"]
        if cond.startswith("robot_mop"):
            name += " (if robot didn't mop)"
        steps.append({"name": name})
        minutes += int(st.get("minutes", 0))
    return steps, minutes, robot


def seed(conn, path: Path, reset: bool = False) -> None:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if reset:
        for t in ("room", "slot", "task", "day_theme", "week", "item", "completion", "move", "day_state", "setting"):
            conn.execute(f"DELETE FROM {t}")

    rooms = {r["id"]: r for r in data["rooms"]}
    for i, r in enumerate(data["rooms"]):
        conn.execute(
            "INSERT INTO room(id,name,floor,kind,zone,robot,shower,never_during,prefer_when,sort) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (r["id"], r["name"], r.get("floor"), r.get("kind"), r.get("zone"),
             0 if r.get("robot") is False else 1, 0 if r.get("shower") is False else 1,
             json.dumps(r.get("never_during", [])), r.get("prefer_when"), i),
        )

    for i, s in enumerate(data["slot_types"]):
        times = s.get("times") or {}
        wd, we = times.get("weekday"), times.get("weekend")
        conn.execute(
            """INSERT INTO slot(id,name,ord,noise,busy,category,anchor,offset_from,offset_minutes,
               wd_on,wd_start,wd_minutes,we_on,we_start,we_minutes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (s["id"], s["name"], i, (s.get("rules") or {}).get("noise"), 1 if s.get("busy") else 0,
             s.get("category"), s.get("anchor"), s.get("offset_from"), s.get("offset_minutes"),
             1 if wd else 0, (wd or {}).get("start"), (wd or {}).get("minutes"),
             1 if we else 0, (we or {}).get("start"), (we or {}).get("minutes")),
        )

    routines = data.get("routines", {})
    loads = data.get("laundry_loads", {})
    laundry_slots = []
    for st in data.get("laundry_steps", []):
        if st.get("step") == "start":
            laundry_slots = st.get("slots", [])
    slot_order = [s["id"] for s in data["slot_types"]]
    sort = 0

    def add_task(name, days, *, group=None, room=None, scope="room", steps=(), minutes=10,
                 prefs=(), robot=False, category=None, note=None):
        nonlocal sort
        sort += 1
        conn.execute(
            """INSERT INTO task(name,group_label,room_id,scope,steps,minutes,days,preferred_slots,robot,category,note,sort)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (name, group, room, scope, json.dumps(list(steps)), minutes, json.dumps(days),
             json.dumps(list(prefs)), 1 if robot else 0, category, note, sort),
        )

    # Daily tasks
    for t in data.get("daily", []):
        if t.get("robot"):
            add_task(t["task"], ["daily"], group="Daily", room=t.get("room"), robot=True, minutes=0,
                     note="Roborock")
            continue
        if t.get("ref"):
            steps, minutes, _ = _steps_for_routine(routines, t["ref"], rooms.get(t.get("room")))
            add_task(t["task"], ["daily"], group="Daily", room=t.get("room"), steps=steps, minutes=minutes)
            continue
        if t.get("scope") == "house":
            kind = t.get("room_kind")
            members = [r for r in data["rooms"] if r.get("kind") == kind]
            if t.get("only_if") == "room.shower":
                members = [r for r in members if r.get("shower") is not False and r.get("floor") != 2]
            steps = [{"name": r["name"], "room": r["id"]} for r in members]
            add_task(t["task"], ["daily"], group="Daily", scope="house", steps=steps,
                     minutes=t.get("minutes", 10), prefs=t.get("slots", []))
            continue
        add_task(t["task"], ["daily"], group="Daily", room=t.get("room"),
                 scope="room" if t.get("room") else "none", minutes=t.get("minutes", 10),
                 prefs=t.get("slots", []))

    # Themed weekdays
    for dow in DOW:
        day = (data.get("baseline_week") or {}).get(dow) or {}
        theme = day.get("theme", "")
        conn.execute("INSERT INTO day_theme(dow, theme) VALUES (?,?)", (dow, theme))
        for it in day.get("items") or []:
            if "laundry" in it:
                names = [loads[k]["name"] for k in it["laundry"]]
                label = "Laundry: " + ", ".join(names)
                if it.get("only_if") == "not_done_this_week":
                    label += " (if not done yet)"
                add_task(label, [dow], group=theme, scope="none", category="laundry",
                         steps=[{"name": s} for s in LAUNDRY_STEPS], minutes=23, prefs=laundry_slots)
            elif "routine" in it:
                for rid in it["rooms"]:
                    steps, minutes, robot = _steps_for_routine(routines, it["routine"], rooms.get(rid))
                    note = "Vacuum by Roborock" if robot and rooms[rid].get("robot") is not False else None
                    if robot and rooms[rid].get("robot") is False:
                        steps.append({"name": "Vacuum (by hand)"})
                        minutes += 10
                    add_task(routines[it["routine"]]["name"], [dow], group=theme, room=rid,
                             steps=steps, minutes=minutes, note=note)
            elif "task" in it:
                prefs = []
                if it.get("before_slot") in slot_order:
                    prefs = slot_order[: slot_order.index(it["before_slot"])]
                add_task(it["task"], [dow], group=theme, scope="none", minutes=it.get("minutes", 10),
                         category=it.get("category"), prefs=prefs)
    conn.commit()
