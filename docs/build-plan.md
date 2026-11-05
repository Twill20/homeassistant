# Home Rhythm: Cleaning, Laundry and Meal Planner

**Recommended architecture and build plan**

A planner built around one person (Mom) that:

- holds a **baseline weekly plan**: what she intends to do and when
- turns that plan into a **live week** she can check off, drag around, snooze, skip or roll forward
- **runs the Roborock** on schedule, handles the prep (doors and gates), and records failures
- reads the **family calendar** so event‑driven tasks (uniforms before games) and time windows (kids at school) happen on their own
- sends **gentle, actionable nudges** and never nags about being "behind"
- ends each week with a **scorecard** you design together

---

## 1. Recommendation: a hybrid system

| Layer | What it does | Built with |
|---|---|---|
| **The brain**: Planner app | Rooms, tasks, frequencies, slots, week board, drag‑and‑drop, scorecard, rescheduling logic | Small custom web app (PWA) + SQLite |
| **The hands**: Home Assistant | Roborock control, door/gate sensors, phone notifications with action buttons, calendar feed, presence/school schedule | Your existing HA instance |
| **The glue** | Planner calls HA to start vacuum runs and send notifications; HA calls back with button taps, vacuum results and errors | HA REST/WebSocket API + webhooks |

### Why not build it purely in Home Assistant?
HA is great for devices and automations, but its dashboards and to‑do lists are poor at the things she cares about most:
dragging tasks between time slots, keeping a baseline plan separate from what actually happened, "reassign everything I missed",
rolling a week forward, and scorecards. You would end up fighting YAML and Lovelace cards indefinitely.

### Why not a standalone app with no HA?
The Roborock, door sensors, presence and actionable phone notifications already live in HA. Re‑implementing them is wasted work.

### Hosting and remote access
- Package the planner as a **Home Assistant add‑on** (a Docker container) with **Ingress** enabled. It then:
  - appears in the HA sidebar and in the **HA Companion app** on her phone
  - is reachable remotely through your existing HA remote access (Nabu Casa, or Tailscale), with **no second login and nothing exposed to the internet**
  - is backed up with HA's normal backups (SQLite file in `/data`)
- If HA runs on a separate box, the same container can run in Docker on the home computer.
- It works as a **PWA** ("Add to Home Screen"), so it feels like a native app. Native iOS/Android apps are not needed.

### Suggested tech stack (boring on purpose, so it's easy to change)
- **Backend:** Python + FastAPI + SQLite (via SQLModel/SQLAlchemy). Python matches HA's ecosystem.
- **Frontend:** SvelteKit or React + a drag‑and‑drop library (e.g. `dnd-kit`/`svelte-dnd-action`), mobile‑first.
- **Scheduler:** APScheduler inside the backend for slot reminders and vacuum kick‑offs (or HA automations that call the app).
- **Config as data:** rooms, doors, slots and task templates live in the DB but can be seeded and exported from YAML (see `data/house.example.yaml`). This lets you version‑control "the house".

---

## 2. Core concepts (the data model)

```
Room ──< Connection >── Room          (door / gate / open; optional HA sensor)
Room ── roborock_segment_id
TaskTemplate  (name, room?, minutes, target frequency, preferred slots, noise level, who, category)
Routine       (named group of TaskTemplates, e.g. "Kitchen reset", "Girls' bathroom deep clean")
SlotType      (e.g. "Early AM – before littles wake", "After school drop‑off", "Nap time", "Evening")
SlotInstance  (date + SlotType + capacity in minutes; generated per week, can be closed for a day)
BaselinePlan  (the ideal week: routines/tasks pinned to SlotTypes on weekdays)
WeekPlan      (a copy of the baseline for a specific week, plus rollovers)
Occurrence    (one scheduled instance of a task: planned → done | snoozed | moved | skipped | failed | rolled)
VacuumRun     (rooms requested, prep checklist, started/finished, result, error code, rooms actually cleaned)
CalendarRule  ("before any event tagged Soccer Game: wash <kid>'s uniform, due 12h prior")
Quota         ("<kid> laundry: 3×/week", "Mailbox: 3×/week")
Meal          (planned dinner, prep session, recipe link, status: prepped / cooked / slipped)
```

Key ideas:

1. **Baseline vs. live week.** The baseline is never changed by what happens day to day. Each Sunday (or on demand) a new week is generated from the baseline.
   At week rollover she picks: **"Start fresh"** (new copy of baseline) or **"Carry over"** (baseline + unfinished items, which she can triage).
2. **Frequency targets drive "what's next."** Each room or task has a target (e.g. every 7 days). A *due score* = days since last done ÷ target.
   The "Next up" list sorts by due score, filtered to tasks that fit the current slot (time left, noise allowed, room accessible).
3. **Slots have rules.** Nap time means quiet tasks only, and no vacuum near the nursery. Kids' rooms are preferred while those kids are at school.
   Early AM is laundry starts. Each slot has a minute capacity, so the planner can tell when a day is over‑full.
4. **Nothing ever goes "overdue" in red.** Missed items become *unplaced* and wait for her. The language is "ready when you are", not "behind".

---

## 3. The rescheduling toolbox (her pain points)

| Action | What happens |
|---|---|
| **Check off** | Marks done and updates "last cleaned" for the room |
| **Snooze** (15m / 1h / later today) | Re‑notifies once; never escalates |
| **Slide** | Move to the next slot of the same type, or drag anywhere on the week board |
| **"Reassign everything I missed"** | Places all unplaced items into the next open slots by due score and capacity. Shows a preview she can accept or tweak. |
| **Skip this week** | Item marked *skipped* (not *missed*). It counts neutrally on the scorecard. |
| **Light week / blanket skip** | "Skip all *deep clean* tasks this week" or "Only essentials Thu–Sat". Frees capacity and replans. |
| **Close a slot / day** | "Sick day", "Doctor appt", and so on: its items flow to the unplaced tray |
| **Roll to next week** | Moves selected items into next week's plan |

**Notification policy (configurable):** at most one nudge per slot, at the slot start ("Nap time: 45 min available. Suggested: Kitchen reset + start load for Emma").
Buttons: **Done ✓ · Snooze · Move to next slot · Skip**. Quiet hours. A "do not disturb today" switch. No "you're behind" messages, ever.

---

## 4. Roborock orchestration

**Room graph.** Rooms are nodes. Doors and gates are edges, each with a state (open / closed / unknown, optionally from a contact sensor).
A breadth‑first search from the dock's room shows which rooms the robot can reach right now.

**Run flow:**
1. Planner picks rooms that are due and allowed in this slot (e.g. kids' rooms during school hours, never the nursery during nap).
2. **Prep notification** ~15 min before: *"Vacuum at 10:00: Living, Playroom, Girls' room. Please: open playroom gate, open girls' door, pick up floor toys, check water tank."*
   with buttons **Ready ✓ / Delay 30m / Skip run**.
3. If door sensors exist and show the path is blocked, it warns or drops unreachable rooms.
4. HA starts segment cleaning (`vacuum.send_command` → `app_segment_clean` with segment IDs, or the integration's room‑clean action, depending on your HA version).
5. HA automations watch the vacuum state and error sensors (water tank empty, dustbin, stuck, can't reach room) and POST results back to the planner.
6. On failure: the run is logged with the reason, the rooms clean late, and a **gentle retry suggestion** is offered ("Refill tank and retry remaining 2 rooms?").
7. Rooms cleaned update their "last vacuumed / mopped" dates.

**Learning over time:** failure stats by reason, room and time ("Girls' room fails 40% of the time: door usually closed") feed the recommendations.

---

## 5. Calendar, laundry, mailbox, meals

- **Calendar:** Skylight syncs *from* source calendars (Google, iCloud, Outlook) and has no public API. Connect the **same source calendar** to HA (Google Calendar integration or an ICS feed),
  then use HA or the planner to read events. Tag events by keyword ("Soccer", "Practice", "Game").
  Rules generate tasks with deadlines, e.g. *"Uniform washed: due 12h before Game"* or *"Practice clothes: after Practice, before next Practice"*.
- **School schedule:** a simple school‑days calendar (or HA schedule helper) defines when older kids are out, which opens the "kids' rooms" window.
- **Laundry quotas:** per‑kid "N loads/week" with preferred slots (early AM). The scorecard shows 2/3 ✓.
- **Mailbox:** a kid task with a quota (3×/week). It can stay in Skylight for the kids, or the planner can mirror it there later.
- **Meals:** start simple. A dinner per night, a weekend **prep session** routine, and statuses (prepped / cooked / slipped → slide to another night).
  Add a "recipe inbox": paste a YouTube or web link and drag it onto a night. HEB ordering stays in her existing app for now.

---

## 6. Phased build plan

Each phase is usable on its own. Ship, let her use it for a week or two, gather feedback, then iterate.

### Phase 0: Discovery (the couples part, 1–2 evenings)
- [ ] Answer `docs/questions-for-her.md` together
- [ ] Walk the house: list rooms, doors and gates; sketch the connection map; fill in `data/house.example.yaml`
- [ ] In the Roborock app: confirm the room split, name rooms to match, and note per‑room suction/mop settings
- [ ] List every recurring task with an honest frequency and a time estimate
- [ ] Define slot types and their typical times and capacities for each weekday

### Phase 1: Home Assistant foundation (quick wins, no app yet)
- [ ] Confirm the Roborock integration and list entities (vacuum, error sensor, water/dock sensors)
- [ ] Get room/segment IDs (`roborock.get_maps` or the integration's room list)
- [ ] Script: `script.vacuum_rooms` (input: list of rooms) with prep notification and Ready/Delay/Skip buttons
- [ ] Automation: notify on vacuum error with a friendly message and log it
- [ ] Install the HA Companion app on her phone; set up remote access (Nabu Casa or Tailscale)
- [ ] Connect the family source calendar to HA

### Phase 2: Planner MVP
- [ ] Rooms, task templates, routines, slot types (seeded from YAML)
- [ ] Baseline week editor
- [ ] Live week board (mobile‑first): day columns × slot rows, tap to check off, drag to move
- [ ] "Next up" list driven by due score
- [ ] Unplaced tray, plus "Reassign everything I missed" with a preview
- [ ] Packaged as an HA add‑on with ingress

### Phase 3: Nudges and flexibility
- [ ] Slot‑start notifications with Done / Snooze / Move / Skip via HA actionable notifications
- [ ] Skip this week, light‑week mode, close slot/day
- [ ] Week rollover: Start fresh vs. Carry over

### Phase 4: Vacuum in the planner
- [ ] Room graph and reachability; generated prep checklists
- [ ] Vacuum runs scheduled from the planner (respecting nap and school rules)
- [ ] Run history, failure reasons, retry‑remaining‑rooms

### Phase 5: Calendar‑driven tasks and quotas
- [ ] Event keyword rules → tasks with deadlines
- [ ] Per‑kid laundry quotas, mailbox quota
- [ ] School‑hours windows for kids' rooms

### Phase 6: Scorecard and meals
- [ ] Weekly scorecard (designed together): rooms at target, quotas met, vacuum success, streaks, "time bought back" from skips
- [ ] Meal nights, prep session, slipped‑meal sliding, recipe inbox

### Phase 7: Smarts (optional)
- [ ] Recommendation tuning from history (best slots per task, failure patterns)
- [ ] Natural‑language assistant via the Claude API: "I'm wiped today, push everything non‑essential to the weekend", or "add this recipe to Thursday"
- [ ] Door/gate contact sensors to automate prep checks

---

## 7. Try before you build (cheap experiments)

Before writing much code, you can test how she likes certain interactions using existing tools:
- **Donetick** (open‑source chore app with an HA integration): recurring chores and assignees
- **Grocy** (HA add‑on): chores with frequencies, plus meal planning

Neither handles slot‑based drag‑and‑drop planning or Roborock prep, but a week with one will show what she loves and what she hates. That is useful input for Phase 2.

---

## 8. Lessons from other apps to design around

| Common failure | Our rule |
|---|---|
| Rigid recurrence: missing Tuesday breaks the chain | Frequency targets (every ~7 days), not fixed dates; sliding is first‑class |
| Overdue lists pile up in red and guilt‑trip | No "overdue" state. Missed items sit in a neutral tray, and one tap replans them. |
| Moving things takes 5 taps | Drag on the board; "move to next slot" is one tap from the notification |
| Notifications escalate | One nudge per slot, snooze never repeats more than once, DND switch |
| Plan and reality get mixed | Baseline plan is separate from the live week; "start fresh" is always available |
| Too much setup before value | Phase 1 delivers vacuum + prep notifications from HA alone |
| Kids' and adult tasks in one cluttered list | Her view is hers; kids' chores stay in Skylight unless she wants them here |
