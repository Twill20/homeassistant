# Decision log

Her answers, and what each one means for the design. Add new entries at the top as feedback comes in.

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
