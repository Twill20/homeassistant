# Decision log

Her answers, and what each one means for the design. Add new entries at the top as feedback comes in.

## 2026-11-08: Floor plan and launch target

- **Floor plan** (`docs/notes/floor-plan.jpg`): everything is on floor 1 except the **theatre room / guest suite** (floor 2, the only room up there; this is "upstairs" in her list).
  The Roborock map covers floor 1; the theatre is manual. **Georgia's room** (5) was added as a bedroom, and Tuesday now has 6 bedrooms.
  Room placement and door/gate connections were drafted from the plan; guesses are marked `TODO(confirm)` in `data/house.yaml`.
- **Target:** v0.1 (cleaning scheduler only) in her hands **Mon Nov 16**. See build plan §6a.
- **Runs locally at home**; development continues in the cloud until the HA/Roborock work starts.
- **Frontend simplified** to server‑rendered htmx (no build step) for speed and easy tinkering. "Move to…" buttons are used instead of drag‑and‑drop on the phone.

## 2026-11-05: Her weekly routine (notes in `docs/notes/weekly-routine.md`)

Converted into `data/house.yaml`. Design decisions it drove:

- **The baseline week is built from themed days:** Mon kitchen & meals · Tue bedrooms · Wed living areas · Thu bonus rooms · Fri bathrooms · Sat/Sun open for catch‑up.
  The Today screen shows the day's theme as its title. "Last done N days ago" is still tracked per room, so a slid Tuesday bedroom shows its age.
- **Routines are reusable checklists applied to rooms** (Bedroom refresh, Living area clean, Bonus room clean, Bathroom clean, Finishing sprays).
  Applying a routine to 5 bedrooms creates 5 checkable items, so she can finish one room at a time and the rest auto‑slide.
- **Steps the robot can do are vacuum runs, not manual tasks:** daily living room + dog room, Tuesday bedrooms, Wednesday living/dining/entry.
  The "Mop" step only appears if the robot mop was skipped or failed (her "if not using vacuum mop").
- **Laundry is tracked as named loads** assigned to days (twins + Truman Mon, bedding Tue, adults + little girls Wed, rugs + towels + Mom Fri).
  "Towels Tuesday if not done Monday" is a conditional item.
- **Meals: Monday is grocery order + meal prep + crockpot day** (not the weekend, as first assumed).
- **The cleaning caddy becomes a supplies list.** Marking "running low" adds it to the grocery list. The electric scrubber gets a "charge it" reminder the night before bathroom day.
- **Rough load check (estimates):** Tuesday ≈ 230 min of hands‑on work plus daily tasks. That is the heaviest day and needs most of the weekday slots, so it's the first candidate for spreading out (e.g. 2–3 bedrooms Tue, the rest Sat).

## 2026-11-05: Second round of answers

| # | Her answer | Design decision |
|---|---|---|
| 1 | Digest **right after the girls go to sleep** | The digest is sent when she taps "Girls are down" (or at that slot's usual time if she doesn't tap). |
| 2 | Slot times are **a setting**; weekends differ | **Settings → Slots** screen with two schedules: **Weekday** (Mon–Fri) and **Weekend** (Sat–Sun). A slot can be turned off for one day type (e.g. "After Truman leaves" is weekdays only). Per‑day overrides can come later if needed. |
| 3 | Anchors by **tap** | Big buttons on Today: **Girls are up · Gigi is down · Girls are down**. Each tap shifts that slot and the slots that follow it. No HA sensors needed. |
| 4 | Truman leaves **weekdays at 8:30** | "After Truman leaves" = weekdays from 08:30. |
| 5 | **Daily digest only** for now | Slot‑start nudges are off. The only other alerts are the three vacuum blockers. |
| 6 | OK to install the **HA app just for notifications** | Notification route A: the HA Companion app delivers notifications with action buttons. |
| 7 | Whole‑house tasks: **windows, electronics dusting** | Seeded as `scope: house`. Everything else is per room unless she toggles it. |
| 8 | Order emails all go to **one Gmail** | The meals phase can read a Gmail label for HEB, Walmart and Instacart confirmations. |
| 9 | Plans meals **next week** | The meal planner defaults to a next‑week view, with "plan further out" available. |
| 10 | Activity drop‑offs/pickups are **on the calendar with consistent names** | Keyword rules can reliably create busy blocks and laundry deadlines. |


## 2026-11-05: First round of answers

| # | Her answer | Design decision |
|---|---|---|
| 1 | Open to **the day** | Home screen is **Today**: slots in order, the current slot expanded, a "Next up" list for the current slot. The week board is one tap away. |
| 2 | Missed items **move to the next available slot** | **Auto‑slide.** When a slot ends, unchecked items move to the next slot that has room and allows them (noise, room access, kids' schedule). No prompt and no red badges. If nothing fits before Sunday night, the item goes to the "whenever" tray. |
| 3 | **Once‑a‑day summary**: highlights, things to improve, how many moved | **Daily digest** notification (default: after the little girls go to sleep). It covers: done today, rooms refreshed, tomorrow's first slot, *N items moved* (tap to see them), and one gentle suggestion, e.g. "Laundry moved 3 days in a row; try the *after Truman leaves* slot?" No other "you missed" messages. |
| 4 | Some tasks are **whole‑house**, some **by room**; must be toggleable | Each task has `scope: room \| house`. House tasks ("dust everywhere", "floors everywhere") can be done room by room on her schedule, and the app tracks how far along she is per room. A **view toggle** groups Today by *room* or by *task type*. A room's "last cleaned" date counts both. |
| 5 | Slots tied to the family rhythm (list below) | **Slots follow real events, not just clock times.** Each slot has a typical start, plus an optional "it happened" trigger: a tap ("Girls are up") or an HA signal. Later slots shift to match. "Kids' activities" slots come from the calendar and are marked *busy* (no tasks). |
| 6 | Vacuum failures: **right away**: doors closed, stuck, tanks empty | **Immediate notification** for these three types, with a fix hint and **Retry remaining rooms / Later / Skip**. Other errors go into the digest. |
| 7 | Kid chores **stay in Skylight** | Out of scope. Kids' *laundry loads* stay in (she runs them). The mailbox stays in Skylight. |
| 8 | **Meal planning native to this app**, with future planning. Bonus: know whether ingredients were already ordered (HEB, Walmart) | Meals become a first‑class module: recipe library, plan weeks ahead, prep sessions, grocery list with *ordered / have it* status. Order matching is phased in (see build plan §5). |
| 9 | **iPhone**, not really on the HA app | The planner is its **own home‑screen app (PWA)** with its own URL. She never needs the HA app's interface. For notifications with buttons we use one of two routes, still to be decided (see build plan §1). |
| 10 | Week starts **Monday**, **starts fresh**, but always show **time since last done** | Each Monday the week is built from the baseline. Nothing carries over, but **"last done N days ago"** is shown on every task and room, and it drives priority. Unfinished items reappear naturally because they're now *more* due. |

### Slot list (from her, in daily order)

1. Before Truman wakes up
2. After Truman leaves
3. Little girls wake up
4. ~2 hours after the girls are up and settled
5. Lunchtime
6. Gigi's naptime (2nd youngest)
7. Early evening
8. Kids' activities: transport required *(busy, from calendar)*
9. Dinner time
10. After the little girls go to sleep
