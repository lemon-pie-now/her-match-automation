"""Build the small browser data file used by the static Her Match site."""
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "events.csv"
OUTPUT = Path(__file__).with_name("events.js")


def main() -> None:
    now = datetime.now(timezone.utc)
    events = []
    with SOURCE.open(encoding="utf-8", newline="") as source:
        for row in csv.DictReader(source):
            start = datetime.fromisoformat(row["start_time_utc"])
            if start < now or row["status"].upper() == "CANCELLED":
                continue
            events.append({
                "id": row["event_id"], "title": row["title"],
                "sport": row["sport"], "competition": row["competition"],
                "start": row["start_time_utc"], "end": row["end_time_utc"],
                "location": row["location"], "url": row["official_url"],
            })
    events.sort(key=lambda event: event["start"])
    OUTPUT.write_text(
        "window.HER_MATCH_EVENTS = "
        + json.dumps(events, ensure_ascii=False, indent=2)
        + ";\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(events)} upcoming events to {OUTPUT}")


if __name__ == "__main__":
    main()
