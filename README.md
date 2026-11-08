# Home Rhythm

A calm cleaning planner for our house: themed days, time slots that follow the family's rhythm,
check‑offs with "last done N days ago", and missed items that quietly slide to the next open slot.
v0.1 covers cleaning and laundry. Roborock, notifications, calendar and meals come next (see the build plan).

- [Notes for Claude / handoff](CLAUDE.md)
- [Architecture and build plan](docs/build-plan.md)
- [Decision log](docs/decisions.md)
- [Questions to answer together](docs/questions-for-her.md)
- [The house model](data/house.yaml) (rooms, slots, routines, themed week). Her original notes and the floor plan are in `docs/notes/`.

## Run it on the home PC (Windows)

Needs Python 3.10 or newer (`py --version`).

1. Get the code: `git clone` this repo (or download the ZIP) to e.g. `C:\HomeRhythm`.
2. Double‑click **`start-home-rhythm.bat`**. The first run creates `.venv` and installs packages.
   The window shows `Home Rhythm on http://localhost:8765`. Leave the window open.
3. Open http://localhost:8765 on the PC to check it.
4. If Windows Firewall asks, allow **Private networks** so phones on the home Wi‑Fi can reach it.

The first start loads `data/house.yaml` into `data/homerhythm.db`. That database holds her history, so back it up now and then.
Changing `house.yaml` later doesn't affect an existing database. Make changes in the app's Settings, or re‑seed with
`.venv\Scripts\python -m homerhythm seed --reset`, which wipes history.

**Start automatically:** press Win+R, run `shell:startup`, and put a shortcut to `start-home-rhythm.bat` in that folder.
**Port clash** with another app: edit the `--port 8765` in the .bat file.

## Put it on her iPhone

**At home (Wi‑Fi):**
1. Find the PC's IP: run `ipconfig` and look for the IPv4 address, e.g. `192.168.1.50`.
2. In **Safari** on her iPhone, open `http://192.168.1.50:8765`.
3. Tap Share → **Add to Home Screen**. It opens full‑screen like an app.

**Away from home (Tailscale, free):**
1. Install Tailscale on the PC and on both iPhones, and sign in with the same account on all three.
2. In the Tailscale app, find the PC's name (e.g. `home-pc`).
3. On the phone, open `http://home-pc:8765` and add *that* to the Home Screen instead. It works both at home and away.

There's no login. Anyone on the home Wi‑Fi or your Tailscale network can open it.

## Day‑to‑day

- **Today:** her slots in order, with the current one highlighted. Tap the circle to check something off, or tap an item for its checklist and options:
  **Next slot · Tomorrow · Whenever · Skip this week · Move to…**
- **Girls are up / Gigi is down / Girls are down:** tap when it happens. The slots after it shift to match.
- **Can't use this slot today:** closes the slot and slides its items onward.
- **Missed something?** Nothing to do. When a slot ends, unfinished items move to the next slot with room.
  Daily tasks only slide within their own day. Anything that can't fit before Sunday lands in **Whenever** (Week tab).
- **Recap:** appears on Today after "Girls are down" (or at that slot's time). It shows what got done, what moved, and one suggestion.
- **Monday:** the week starts fresh from the themed plan. "Last done" history carries over.
- **Settings:** weekday and weekend slot times and lengths, task minutes, days and checklists, add tasks.
  After editing, use **Re‑plan rest of this week** to apply the changes now.

## Development

```
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
HOMERHYTHM_NOW=2026-11-17T13:20 HOMERHYTHM_DB=/tmp/demo.db .venv/bin/python -m homerhythm   # pin the clock for testing
```
Settings: `HOMERHYTHM_TZ` (default America/Chicago), `HOMERHYTHM_DB`, `HOMERHYTHM_HOUSE`.
