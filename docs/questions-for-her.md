# Questions to answer together

Answer these over coffee or a date night. Short answers are fine, and "I don't know yet" is a valid answer.

## How she likes to be helped
1. When you open a planning app, what do you want to see first: **today's list**, **the whole week**, or **"what should I do right now"**?
2. What should a notification sound like? Is one nudge at the start of a slot enough? Should there be no notifications during certain hours, or on certain days?
3. When you miss something, what feels best?
   (a) it quietly goes into a "whenever" tray
   (b) it auto‑moves to the next open slot and tells you
   (c) it asks you once at the end of the day
4. Do you want to see counts like "12 of 20 done"? Or does that feel like pressure? What *would* feel rewarding (streaks, rooms "fresh", time saved, a weekly recap)?
5. Should "skipped on purpose" look different from "didn't get to it"?
6. Is there anything in Skylight or another app that you love and want copied exactly? What annoys you most about them?

## The week's rhythm
7. List your typical time slots and roughly how long each is:
   early morning (before the littles wake), after school drop‑off, nap time, afternoon, evening after bedtime. Does this differ by weekday?
8. During nap time, what is *off limits* (noise, specific rooms, vacuum)?
9. Which days are usually wrecked (activities, appointments)? Should those default to "light"?
10. When does a "week" start for you: Sunday or Monday? When do you want to plan it (e.g. Sunday evening)?
11. At week's end, what's your default: start fresh, or carry over what's unfinished?

## Rooms and cleaning
12. Which rooms matter most to keep "always ready"? Which can slide?
13. For each room: how often for a quick tidy, a full clean, and a deep clean? (We'll fill in `data/house.example.yaml` together.)
14. Do you like cleaning **room by room** (finish a room) or **task by task** (dust everything, then floors everywhere)?
15. Should tasks have time estimates you can adjust, so the planner never overfills a nap?
16. Are there tasks only you do, ones I (husband) do, and ones the older kids do? Should the app show mine to you?

## Roborock
17. Which rooms should the robot do, and how often? Vacuum only, or mop too?
18. When is it OK for it to run: while we're out, during school, never during nap?
19. What prep is needed for each room (doors, gates, toys off floor, chairs up, rugs)?
20. What usually makes it fail (tank, stuck on cords, closed door, dock full)? How do you want to hear about a failure: right away, or in a quiet summary?
21. Would you be willing to add door/gate sensors (cheap Zigbee contact sensors) later so prep can be checked automatically?

## Laundry and kids
22. For each kid: how many loads per week, and are there preferred days or slots?
23. Which activities need clothes ready (soccer games, practices, training)? How far ahead must they be clean?
24. Mailbox: which kid, how many times a week, and should it stay in Skylight?
25. Should kid chores live in this app at all, or stay in Skylight and only *show* here?

## Calendar
26. Which calendars feed Skylight (Google, iCloud, Outlook)? Can we connect that same source to Home Assistant?
27. How are events named? Is "Soccer" or "Game" consistent enough to trigger reminders automatically?

## Meals
28. Which meal planning and HEB apps do you use? What do they do well, and where do they fall short?
29. Do you want meals in this planner at all at first, or later?
30. When a meal slips, what usually happens: it moves to tomorrow, gets frozen, or gets dropped?
31. Would a "recipe inbox" (paste a YouTube or web link, drag it to a night) be useful?

## Access and devices
32. Phone type (iPhone or Android)? Do you already use the Home Assistant app?
33. Would a wall tablet or kitchen display be nice later, next to Skylight?

---

## Round 2 (after her first answers; see `docs/decisions.md`)

1. **Digest timing:** is right after the little girls go to sleep the best time for the daily summary, or later once things are quiet?
2. **Slot start times:** roughly when does each slot start, and how long is it? Do any slots differ on weekends?
3. **Anchors:** would you tap "Girls are up" / "Gigi is down" so later slots shift? Or should the app just use typical times?
4. **Truman:** which days does Truman leave, and roughly when? (This defines the "after Truman leaves" slot.)
5. **Slot nudges:** digest only to start? Or also a single "here's this slot's plan" nudge at certain slots (e.g. Gigi's nap)?
6. **Notification app:** OK to install the Home Assistant app *only* so notifications can have Done / Snooze / Move buttons? You'd never need to open it.
7. **House vs. room:** which tasks do you think of as "across the whole house" (dusting, floors, trash, windows)?
8. **Meals:** which apps do you use today for recipes and planning? Are HEB / Walmart / Instacart order emails going to one Gmail address?
9. **Meals:** how far ahead do you like to plan: next week, or a month?
10. **Kids' activities:** are pickups and drop‑offs already events on the family calendar, with consistent names?
