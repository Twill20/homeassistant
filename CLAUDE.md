# Home Rhythm: notes for Claude

A cleaning, laundry and meal planner built by a husband for his wife, who is the only user.
It runs on the family's **Windows home PC**. **Home Assistant (HA) runs separately on a Raspberry Pi** on the same LAN.
Her iPhone uses the app as a home‑screen web app, at home over Wi‑Fi and away over Tailscale.

Read these first: `docs/decisions.md` (her answers and every design decision, newest first), `docs/build-plan.md`
(architecture and phases), `data/house.yaml` (rooms, slots, routines, themed week), and `README.md` (setup and day‑to‑day use).

## Her preferences (don't break these)
- Calm, never naggy. No "overdue" or red states and no "you're behind" messages. Missed items **auto‑slide** to the next slot with room.
- Notifications: the **daily recap only** (sent when she taps "Girls are down"), plus **immediate** alerts for exactly three vacuum problems:
  door closed / can't reach a room, stuck, tank empty. Everything else goes in the recap.
- The week starts **Monday** and **starts fresh** from the themed baseline. "Last done N days ago" history always carries over.
- Slots follow the family's rhythm (weekday/weekend schedules, tap anchors). Slot times are settings she edits.
- Kid chores (mailbox, etc.) stay in Skylight. Out of scope.
- Use **they/them** for anyone whose pronouns aren't stated. Kids' names appear in data. Keep them out of anything public.

## Code map
- `homerhythm/schedule.py`: slot times, week generation, auto‑slide, moves, completion, recap. **Core logic. Keep it tested.**
- `homerhythm/web.py`: FastAPI routes (async, single shared SQLite connection). `templates/` uses Jinja + htmx `hx-boost`. Every POST redirects back.
- `homerhythm/seed.py`: loads `data/house.yaml` into SQLite on first run.
- `homerhythm/db.py`: schema. The DB lives at `data/homerhythm.db` (git‑ignored). **It holds her real history. Never delete or re‑seed it without asking.**
- `tests/`: pytest. The clock can be pinned with `HOMERHYTHM_NOW=2026-11-17T13:20`.

## Commands (Windows)
```
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest -q
start-home-rhythm.bat                      # runs on http://0.0.0.0:8765
set HOMERHYTHM_DB=%TEMP%\demo.db && set HOMERHYTHM_NOW=2026-11-17T13:20 && .venv\Scripts\python -m homerhythm   # safe test copy
```
Test against a throwaway DB (`HOMERHYTHM_DB`), never the real one. The real app may already be running on port 8765, so use another port for tests.

## Current status
v0.1 is done: Today/Week/Recap/Settings, auto‑slide, Whenever tray, skip, close slot, anchors, slot settings, task editor.
Development branch: `claude/cleaning-schedule-app-2tgb3f`. Commit there. Ask before pushing elsewhere or opening PRs.

## Next: v0.2 (Home Assistant + Roborock), in this order
1. **Connect to HA.** Ask the user to create a long‑lived access token (HA profile → Security) and put it in a git‑ignored `.env`
   (`HA_URL=http://<pi-ip-or-homeassistant.local>:8123`, `HA_TOKEN=...`). Never commit or print the token.
   Check access with `GET /api/` and `GET /api/states`.
2. **Discover the Roborock:** list `vacuum.*` and `sensor.*`/`binary_sensor.*` entities containing "roborock" (status, error, water/tank, dock).
   Get room/segment IDs via the `roborock.get_maps` action, or whatever the installed HA version offers (check the version with `GET /api/config`).
   Put the real entity id, `dock_room`, and `roborock_segment` per room into `data/house.yaml`, with a migration or update for the existing DB.
   The robot map covers floor 1 only. Floor 2 (theatre) is manual.
3. **Vacuum runs from the app:** start a room clean via HA (`vacuum.send_command` / `app_segment_clean` with segment ids, or the
   integration's room action). Add a prep checklist (doors and gates from `connections` in house.yaml) before a run, and log each run with its result.
   Robot items currently show in a "Robot" section that she ticks by hand. Mark them done automatically when a run succeeds.
4. **Notifications through the HA Companion app on her iPhone** (installed only for notifications): `notify.mobile_app_<her_phone>`.
   Send the evening recap, and immediate alerts for the 3 vacuum problems with actions (Retry remaining rooms / Later / Skip).
   Handle action taps through an HA automation that calls a webhook on the planner.
5. Later: calendar rules (uniforms before games, activity busy blocks from the family Google/iCloud calendar that feeds Skylight), meals module, scorecard.

Open questions still in `docs/questions-for-her.md` (e.g. which bath is the girls' bath vs. the littles' bath). Record new answers in `docs/decisions.md`.
