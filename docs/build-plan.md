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

### Hosting and remote access (updated: she's on iPhone and doesn't use the HA app)
- The planner is its **own app on her iPhone home screen** (a PWA added with Safari's "Add to Home Screen"). She never sees the HA interface.
- It runs as a Docker container on the home computer, or as an HA add‑on if HA runs on a Home Assistant OS box. Either way the SQLite file is backed up.
- **Remote access:** recommended is **Tailscale** on both phones plus the home computer, with `tailscale serve` providing an HTTPS address. It's private, there's no port forwarding, and it's free.
  The alternative is a Cloudflare Tunnel with a Cloudflare Access login, if you'd rather not run a VPN app on the phone.
- **Notifications with buttons on iPhone:** two routes:
  - **A. Recommended:** install the HA Companion app **only as the notification channel**. She allows notifications once and never opens the app. iOS shows **Done / Snooze / Move / Skip** buttons, and tapping the notification opens the planner.
  - **B.** Web Push from the PWA itself (iOS 16.4+). No extra app, but tapping only opens the planner. The action buttons aren't reliably supported on iOS.
  - Either way, the planner owns the notification logic, so we can switch routes later.

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
TaskTemplate  (name, scope: room|house, room?, minutes, target frequency, preferred slots, noise level, category)
CompletionLog (task, room, when): source of "last done N days ago"; survives every weekly fresh start
SlotAnchor    (e.g. "Girls are up"): tap or HA signal that shifts the slots after it
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

1. **Baseline vs. live week.** The baseline is never changed by what happens day to day. **Every Monday the week starts fresh** from the baseline.
   Nothing is lost: "last done N days ago" comes from the completion log, so anything she didn't get to comes back *higher* in priority. A manual "carry this into next week" remains as an occasional option.
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

**Default when something is missed (her choice): auto‑slide.** When a slot ends, unchecked items quietly move to the next slot that has room and allows them.
If nothing fits before Sunday night, the item goes to the "whenever" tray. On Monday the week starts fresh.

**Notification policy:**
- Optional single nudge at a slot's start ("Gigi's nap: ~90 min. Suggested: Kitchen reset · Start load (Kid A) · last done 4 days ago"). Buttons: **Done ✓ · Snooze · Move · Skip**.
- **Daily digest** (default: after the little girls go to sleep): what got done, rooms refreshed, **N items moved** (tap to see them), tomorrow's first slot, and **one** gentle improvement idea.
- **Immediate** only for vacuum blockers: door closed, stuck, tank empty.
- Quiet hours, a "do not disturb today" switch, and no "you're behind" messages, ever.

**Today screen (home):** slots in order, with the current slot expanded. Each item shows its time estimate and "last done N days ago".
A toggle groups the screen **by room** or **by task type**. Slots shift when she taps an anchor such as **"Girls are up"**.

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
5. HA automations watch the vacuum state and error sensors and POST results back to the planner.
   **Door closed / can't reach room, stuck, and tank empty notify her immediately** (her choice). Everything else goes into the daily digest.
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
- **Kid chores (including the mailbox) stay in Skylight.** Out of scope for this app.
- **Kids' activities:** calendar events that need transport become **busy** blocks, and the slots around them shrink automatically.

### Meals (native module: her request)
- **Recipe library:** paste a YouTube or web link. The app pulls the title and thumbnail, and pulls ingredients when the page publishes structured recipe data (most recipe sites do; YouTube usually needs a manual or AI‑assisted ingredient list).
- **Future planning:** drag recipes onto dinner nights weeks ahead. **Prep sessions** (e.g. Sunday) are scheduled like any task and linked to the meals they cover.
- **Slippage:** a meal can be marked *cooked*, *slid* (drag to another night), *frozen* or *dropped*. Prepped‑but‑not‑cooked meals show how long they've been in the fridge.
- **Grocery list:** built from upcoming meals. Each ingredient is **need / ordered / have it**, with the store and order date.
- **"Was it ordered already?"**: HEB and Walmart don't offer public APIs for order history, so this is phased in:
  1. **Manual:** after placing an order, tick "ordered at HEB". The list remembers it and shows ✓ on every meal that uses those items.
  2. **Email matching (the realistic automation):** order confirmation and receipt emails from HEB, Walmart and Instacart list the items.
     The app reads a dedicated mail label or folder (Gmail API or IMAP), extracts the item names (with Claude's help for messy formats), and matches them to the grocery list. She confirms any uncertain matches.
  3. **Later:** watch for any official integrations or her other meal apps' export features.

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
- [ ] Rooms, task templates (room/house scope), routines, her 10 slot types (seeded from YAML)
- [ ] Completion log, plus "last done N days ago" everywhere
- [ ] **Today screen** (home) with the by‑room / by‑task toggle; week board one tap away with drag‑and‑drop
- [ ] "Next up" list driven by due score
- [ ] Auto‑slide of missed items to the next fitting slot; "whenever" tray
- [ ] Monday fresh start from the baseline
- [ ] Home‑screen PWA on her iPhone, served over Tailscale HTTPS

### Phase 3: Nudges and flexibility
- [ ] Daily digest (done, moved count, one improvement idea)
- [ ] Optional slot‑start nudges with Done / Snooze / Move / Skip (via the HA Companion app as a notification channel only)
- [ ] Slot anchors ("Girls are up") that shift later slots
- [ ] Skip this week, light‑week mode, close slot/day

### Phase 4: Vacuum in the planner
- [ ] Room graph and reachability; generated prep checklists
- [ ] Vacuum runs scheduled from the planner (respecting nap and school rules)
- [ ] Run history, failure reasons, retry‑remaining‑rooms

### Phase 5: Calendar‑driven tasks and quotas
- [ ] Event keyword rules → tasks with deadlines (uniforms before games, practice clothes between practices)
- [ ] Activity transport events → busy blocks
- [ ] Per‑kid laundry quotas
- [ ] School‑hours windows for kids' rooms

### Phase 6: Meals
- [ ] Recipe library from links; dinner plan weeks ahead; prep sessions linked to meals
- [ ] Cooked / slid / frozen / dropped statuses; days‑in‑fridge for prepped meals
- [ ] Grocery list with need / ordered / have‑it (manual)
- [ ] Order‑email matching for HEB, Walmart and Instacart

### Phase 6b: Scorecard
- [ ] Weekly scorecard (designed together): rooms at target, quotas met, vacuum success, items moved, "time bought back" from skips

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
