# Her Match website

A dependency-free MVP for discovering professional women's sports schedules and exporting selected matches to Apple Calendar, Google Calendar, Outlook, or any other calendar that accepts `.ics` files.

## Run locally

```bash
python3 website/build_events.py
python3 -m http.server 8000 --directory website
```

Then open `http://localhost:8000`.

Run `build_events.py` after refreshing `data/events.csv` to update the website schedule.
