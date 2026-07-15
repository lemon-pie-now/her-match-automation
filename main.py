from __future__ import annotations

import csv
import hashlib
import os
import sys
from dataclasses import asdict, dataclass, fields
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv
from icalendar import Calendar


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"

EVENTS_FILE = DATA_DIR / "events.csv"
CHANGES_FILE = DATA_DIR / "changes.csv"
NEWSLETTER_FILE = OUTPUT_DIR / "newsletter.md"


@dataclass
class SportsEvent:
    event_id: str
    source_uid: str
    sport: str
    competition: str
    title: str
    start_time_utc: str
    end_time_utc: str
    location: str
    description: str
    official_url: str
    status: str
    source_url: str
    last_checked_utc: str


def ensure_directories() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def read_required_setting(name: str) -> str:
    value = os.getenv(name, "").strip()

    if not value:
        raise ValueError(
            f"Missing required setting {name}. "
            f"Add it to your .env file."
        )

    return value


def normalize_datetime(value: Any) -> datetime:
    """
    Convert a date or datetime from an ICS file into a timezone-aware
    UTC datetime.
    """
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, date):
        result = datetime.combine(value, time.min)
    else:
        raise TypeError(f"Unsupported date value: {value!r}")

    if result.tzinfo is None:
        # Treat timezone-free values as UTC initially.
        # Later, a source-specific timezone can be added if necessary.
        result = result.replace(tzinfo=timezone.utc)

    return result.astimezone(timezone.utc)


def optional_component_text(component: Any, property_name: str) -> str:
    value = component.get(property_name)

    if value is None:
        return ""

    return str(value).strip()


def create_event_id(
    competition: str,
    source_uid: str,
    title: str,
    start_time_utc: datetime,
) -> str:
    """
    Prefer the official ICS UID. Add competition information so that
    identical UIDs from unrelated calendars cannot collide.
    """
    identifying_value = source_uid or (
        f"{title}|{start_time_utc.isoformat()}"
    )

    raw_value = f"{competition}|{identifying_value}"
    return hashlib.sha256(raw_value.encode("utf-8")).hexdigest()[:24]


def load_calendar_bytes(source: str) -> bytes:
    """
    Read an ICS calendar from:
    - an https:// or http:// URL;
    - a webcal:// subscription URL; or
    - a local file such as sample.ics.
    """
    source = source.strip()

    if source.startswith("webcal://"):
        source = "https://" + source.removeprefix("webcal://")

    if source.startswith(("https://", "http://")):
        response = requests.get(
            source,
            timeout=30,
            headers={
                "User-Agent": (
                    "HerMatchCalendarBot/0.1 "
                    "(event aggregation prototype)"
                )
            },
        )
        response.raise_for_status()
        return response.content

    local_path = Path(source)

    if not local_path.is_absolute():
        local_path = BASE_DIR / local_path

    if not local_path.exists():
        raise FileNotFoundError(
            f"Calendar file was not found: {local_path}"
        )

    return local_path.read_bytes()


def collect_ics_events(
    source: str,
    sport: str,
    competition: str,
) -> list[SportsEvent]:
    calendar_bytes = load_calendar_bytes(source)
    calendar = Calendar.from_ical(calendar_bytes)

    checked_at = datetime.now(timezone.utc).isoformat()
    collected_events: list[SportsEvent] = []

    for component in calendar.walk():
        if component.name != "VEVENT":
            continue

        if component.get("dtstart") is None:
            print(
                "Skipping event without a start date.",
                file=sys.stderr,
            )
            continue

        title = optional_component_text(component, "summary")
        title = title or "Untitled event"

        source_uid = optional_component_text(component, "uid")
        start_time = normalize_datetime(
            component.decoded("dtstart")
        )

        end_time = start_time

        if component.get("dtend") is not None:
            end_time = normalize_datetime(
                component.decoded("dtend")
            )

        event = SportsEvent(
            event_id=create_event_id(
                competition=competition,
                source_uid=source_uid,
                title=title,
                start_time_utc=start_time,
            ),
            source_uid=source_uid,
            sport=sport,
            competition=competition,
            title=title,
            start_time_utc=start_time.isoformat(),
            end_time_utc=end_time.isoformat(),
            location=optional_component_text(
                component,
                "location",
            ),
            description=optional_component_text(
                component,
                "description",
            ),
            official_url=optional_component_text(
                component,
                "url",
            ),
            status=(
                optional_component_text(component, "status")
                or "CONFIRMED"
            ),
            source_url=source,
            last_checked_utc=checked_at,
        )

        collected_events.append(event)

    return collected_events


def load_existing_events() -> dict[str, SportsEvent]:
    if not EVENTS_FILE.exists():
        return {}

    existing_events: dict[str, SportsEvent] = {}

    with EVENTS_FILE.open(
        "r",
        newline="",
        encoding="utf-8",
    ) as file:
        reader = csv.DictReader(file)

        for row in reader:
            event = SportsEvent(**row)
            existing_events[event.event_id] = event

    return existing_events


def event_business_values(event: SportsEvent) -> dict[str, str]:
    """
    Return fields that represent meaningful event information.
    Operational fields such as last_checked_utc are excluded.
    """
    values = asdict(event)
    values.pop("last_checked_utc", None)
    return values


def compare_events(
    old_event: SportsEvent,
    new_event: SportsEvent,
) -> list[str]:
    changed_fields: list[str] = []

    old_values = event_business_values(old_event)
    new_values = event_business_values(new_event)

    for field_name, old_value in old_values.items():
        if old_value != new_values[field_name]:
            changed_fields.append(field_name)

    return changed_fields


def merge_events(
    existing_events: dict[str, SportsEvent],
    collected_events: list[SportsEvent],
) -> tuple[dict[str, SportsEvent], list[dict[str, str]]]:
    merged_events = dict(existing_events)
    changes: list[dict[str, str]] = []

    for new_event in collected_events:
        old_event = existing_events.get(new_event.event_id)

        if old_event is None:
            changes.append(
                {
                    "detected_at_utc": (
                        datetime.now(timezone.utc).isoformat()
                    ),
                    "event_id": new_event.event_id,
                    "title": new_event.title,
                    "competition": new_event.competition,
                    "change_type": "new_event",
                    "changed_fields": "",
                }
            )
        else:
            changed_fields = compare_events(
                old_event,
                new_event,
            )

            if changed_fields:
                changes.append(
                    {
                        "detected_at_utc": (
                            datetime.now(timezone.utc).isoformat()
                        ),
                        "event_id": new_event.event_id,
                        "title": new_event.title,
                        "competition": new_event.competition,
                        "change_type": "updated_event",
                        "changed_fields": ",".join(changed_fields),
                    }
                )

        merged_events[new_event.event_id] = new_event

    return merged_events, changes


def save_events(events: dict[str, SportsEvent]) -> None:
    field_names = [field.name for field in fields(SportsEvent)]

    ordered_events = sorted(
        events.values(),
        key=lambda event: (
            event.start_time_utc,
            event.competition,
            event.title,
        ),
    )

    with EVENTS_FILE.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=field_names,
        )
        writer.writeheader()

        for event in ordered_events:
            writer.writerow(asdict(event))


def append_changes(changes: list[dict[str, str]]) -> None:
    if not changes:
        return

    field_names = [
        "detected_at_utc",
        "event_id",
        "title",
        "competition",
        "change_type",
        "changed_fields",
    ]

    file_exists = CHANGES_FILE.exists()

    with CHANGES_FILE.open(
        "a",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=field_names,
        )

        if not file_exists:
            writer.writeheader()

        writer.writerows(changes)


def event_link(event: SportsEvent) -> str:
    if event.official_url:
        return f"[{event.title}]({event.official_url})"

    return event.title


def generate_newsletter(
    events: dict[str, SportsEvent],
    timezone_name: str,
    days_ahead: int,
) -> int:
    local_timezone = ZoneInfo(timezone_name)
    now_local = datetime.now(local_timezone)
    date_limit = now_local + timedelta(days=days_ahead)

    upcoming_events: list[
        tuple[datetime, SportsEvent]
    ] = []

    for event in events.values():
        start_utc = datetime.fromisoformat(
            event.start_time_utc
        )
        start_local = start_utc.astimezone(local_timezone)

        if now_local <= start_local < date_limit:
            upcoming_events.append((start_local, event))

    upcoming_events.sort(
        key=lambda item: (
            item[0],
            item[1].sport,
            item[1].competition,
        )
    )

    lines = [
        "# Her Match",
        "",
        "## Women's sports coming up",
        "",
        (
            f"Events scheduled from "
            f"{now_local.strftime('%B %d, %Y')} through "
            f"{date_limit.strftime('%B %d, %Y')}."
        ),
        "",
    ]

    current_date: date | None = None

    for local_start, event in upcoming_events:
        event_date = local_start.date()

        if event_date != current_date:
            current_date = event_date
            lines.extend(
                [
                    f"## {local_start.strftime('%A, %B %d')}",
                    "",
                ]
            )

        time_text = local_start.strftime("%-I:%M %p")
        location_text = (
            f" · {event.location}"
            if event.location
            else ""
        )

        lines.extend(
            [
                (
                    f"- **{time_text} · {event.sport} · "
                    f"{event.competition}**"
                ),
                f"  {event_link(event)}{location_text}",
                "",
            ]
        )

    if not upcoming_events:
        lines.extend(
            [
                (
                    "No events were found in the selected "
                    "date range."
                ),
                "",
            ]
        )

    NEWSLETTER_FILE.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    return len(upcoming_events)


def main() -> None:
    load_dotenv()
    ensure_directories()

    source = read_required_setting("ICS_URL")
    sport = read_required_setting("SPORT")
    competition = read_required_setting("COMPETITION")

    timezone_name = os.getenv(
        "DISPLAY_TIMEZONE",
        "America/Toronto",
    ).strip()

    try:
        days_ahead = int(os.getenv("DAYS_AHEAD", "14"))
    except ValueError as exc:
        raise ValueError(
            "DAYS_AHEAD must be a whole number."
        ) from exc

    print(f"Collecting events from {competition}...")

    collected_events = collect_ics_events(
        source=source,
        sport=sport,
        competition=competition,
    )

    existing_events = load_existing_events()

    merged_events, changes = merge_events(
        existing_events=existing_events,
        collected_events=collected_events,
    )

    save_events(merged_events)
    append_changes(changes)

    newsletter_count = generate_newsletter(
        events=merged_events,
        timezone_name=timezone_name,
        days_ahead=days_ahead,
    )

    new_event_count = sum(
        change["change_type"] == "new_event"
        for change in changes
    )
    updated_event_count = sum(
        change["change_type"] == "updated_event"
        for change in changes
    )

    print(f"Collected: {len(collected_events)}")
    print(f"New events: {new_event_count}")
    print(f"Updated events: {updated_event_count}")
    print(f"Newsletter events: {newsletter_count}")
    print(f"Event database: {EVENTS_FILE}")
    print(f"Change log: {CHANGES_FILE}")
    print(f"Newsletter draft: {NEWSLETTER_FILE}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Automation failed: {error}", file=sys.stderr)
        raise