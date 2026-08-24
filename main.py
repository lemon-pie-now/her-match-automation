from __future__ import annotations

import csv
import hashlib
import html
import json
import os
import re
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

SOURCES_FILE = DATA_DIR / "sources.csv"
EVENTS_FILE = DATA_DIR / "events.csv"
CHANGES_FILE = DATA_DIR / "changes.csv"
NEWSLETTER_FILE = OUTPUT_DIR / "newsletter.md"


@dataclass(frozen=True)
class CalendarSource:
    """
    Configuration for one league or competition calendar.

    source_id must remain stable even if the calendar URL or displayed
    competition name changes.
    """

    source_id: str
    source: str
    sport: str
    competition: str
    source_type: str = "ics"


@dataclass
class SportsEvent:
    event_id: str
    source_id: str
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


def normalize_boolean(value: str, default: bool = True) -> bool:
    cleaned_value = value.strip().lower()

    if not cleaned_value:
        return default

    if cleaned_value in {"1", "true", "yes", "y", "on"}:
        return True

    if cleaned_value in {"0", "false", "no", "n", "off"}:
        return False

    raise ValueError(
        f"Invalid enabled value {value!r}. "
        "Use true/false, yes/no, or 1/0."
    )


def load_calendar_sources() -> list[CalendarSource]:
    """
    Load enabled calendar sources from data/sources.csv.

    Required columns:
        source_id, source, sport, competition

    Optional column:
        enabled, source_type
    """
    if not SOURCES_FILE.exists():
        raise FileNotFoundError(
            f"Calendar source file was not found: {SOURCES_FILE}\n"
            "Create it with these columns:\n"
            "source_id,source,sport,competition,enabled"
        )

    calendar_sources: list[CalendarSource] = []
    seen_source_ids: set[str] = set()

    with SOURCES_FILE.open(
        "r",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        reader = csv.DictReader(file)

        required_columns = {
            "source_id",
            "source",
            "sport",
            "competition",
        }
        actual_columns = set(reader.fieldnames or [])
        missing_columns = required_columns - actual_columns

        if missing_columns:
            missing_text = ", ".join(sorted(missing_columns))
            raise ValueError(
                f"{SOURCES_FILE} is missing required columns: "
                f"{missing_text}"
            )

        for row_number, row in enumerate(reader, start=2):
            enabled = normalize_boolean(
                row.get("enabled", ""),
                default=True,
            )

            if not enabled:
                continue

            source_id = row.get("source_id", "").strip()
            source = row.get("source", "").strip()
            sport = row.get("sport", "").strip()
            competition = row.get("competition", "").strip()
            source_type = (
                row.get("source_type", "ics").strip().lower()
                or "ics"
            )

            if source_type not in {"ics", "wpbl_api", "wsl_official"}:
                raise ValueError(
                    f"Unsupported source_type {source_type!r} "
                    f"on row {row_number}."
                )

            missing_values = [
                name
                for name, value in {
                    "source_id": source_id,
                    "source": source,
                    "sport": sport,
                    "competition": competition,
                }.items()
                if not value
            ]

            if missing_values:
                missing_text = ", ".join(missing_values)
                raise ValueError(
                    f"Incomplete source on row {row_number}. "
                    f"Missing: {missing_text}"
                )

            if source_id in seen_source_ids:
                raise ValueError(
                    f"Duplicate source_id {source_id!r} "
                    f"on row {row_number}."
                )

            seen_source_ids.add(source_id)

            calendar_sources.append(
                CalendarSource(
                    source_id=source_id,
                    source=source,
                    sport=sport,
                    competition=competition,
                    source_type=source_type,
                )
            )

    if not calendar_sources:
        raise ValueError(
            f"No enabled calendar sources were found in {SOURCES_FILE}."
        )

    return calendar_sources


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
        result = result.replace(tzinfo=timezone.utc)

    return result.astimezone(timezone.utc)


def optional_component_text(component: Any, property_name: str) -> str:
    value = component.get(property_name)

    if value is None:
        return ""

    return str(value).strip()


def create_event_id(
    source_id: str,
    source_uid: str,
    recurrence_id: str,
    title: str,
    start_time_utc: datetime,
) -> str:
    """
    Build a stable event ID.

    The source_id is intentionally used instead of the competition name
    or calendar URL. This allows either display value to change without
    creating duplicate events.
    """
    if source_uid:
        identifying_value = source_uid

        if recurrence_id:
            identifying_value = (
                f"{identifying_value}|{recurrence_id}"
            )
    else:
        identifying_value = (
            f"{title}|{start_time_utc.isoformat()}"
        )

    raw_value = f"{source_id}|{identifying_value}"

    return hashlib.sha256(
        raw_value.encode("utf-8")
    ).hexdigest()[:24]


def load_calendar_bytes(source: str) -> bytes:
    """
    Read an ICS calendar from:
    - an https:// or http:// URL;
    - a webcal:// subscription URL; or
    - a local file such as data/sample.ics.
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
                    "HerMatchCalendarBot/0.2 "
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
    calendar_source: CalendarSource,
) -> list[SportsEvent]:
    calendar_bytes = load_calendar_bytes(
        calendar_source.source
    )
    calendar = Calendar.from_ical(calendar_bytes)

    checked_at = datetime.now(timezone.utc).isoformat()
    collected_events: list[SportsEvent] = []

    for component in calendar.walk():
        if component.name != "VEVENT":
            continue

        if component.get("dtstart") is None:
            print(
                (
                    "Skipping event without a start date from "
                    f"{calendar_source.competition}."
                ),
                file=sys.stderr,
            )
            continue

        title = (
            optional_component_text(component, "summary")
            or "Untitled event"
        )
        source_uid = optional_component_text(component, "uid")
        recurrence_id = optional_component_text(
            component,
            "recurrence-id",
        )

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
                source_id=calendar_source.source_id,
                source_uid=source_uid,
                recurrence_id=recurrence_id,
                title=title,
                start_time_utc=start_time,
            ),
            source_id=calendar_source.source_id,
            source_uid=source_uid,
            sport=calendar_source.sport,
            competition=calendar_source.competition,
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
            source_url=calendar_source.source,
            last_checked_utc=checked_at,
        )

        collected_events.append(event)

    return collected_events


def wpbl_acf_value(record: dict[str, Any], field_name: str) -> Any:
    """Return the raw value from a WPBL Advanced Custom Fields record."""
    field = record.get("acf", {}).get(field_name)

    if not isinstance(field, dict):
        return field

    return field.get("value")


def load_wpbl_records(source: str) -> list[dict[str, Any]]:
    """Load every published record from a paginated WPBL REST endpoint."""
    records: list[dict[str, Any]] = []
    page = 1

    while True:
        response = requests.get(
            source,
            params={"per_page": 100, "page": page},
            timeout=30,
            headers={
                "User-Agent": (
                    "HerMatchCalendarBot/0.3 "
                    "(women's sports calendar)"
                )
            },
        )
        response.raise_for_status()
        page_records = response.json()

        if not isinstance(page_records, list):
            raise ValueError(
                "The WPBL schedule API returned an unexpected response."
            )

        records.extend(page_records)
        total_pages = int(response.headers.get("X-WP-TotalPages", "1"))

        if page >= total_pages:
            return records

        page += 1


def collect_wpbl_events(
    calendar_source: CalendarSource,
) -> list[SportsEvent]:
    """Collect games from the official WPBL WordPress schedule API."""
    records = load_wpbl_records(calendar_source.source)
    checked_at = datetime.now(timezone.utc).isoformat()
    collected_events: list[SportsEvent] = []

    for record in records:
        game_date = str(wpbl_acf_value(record, "game_date") or "")
        game_time = str(wpbl_acf_value(record, "game_time") or "")
        timezone_name = str(
            wpbl_acf_value(record, "game_timezone")
            or "America/Chicago"
        )

        if not game_date or not game_time:
            print(
                "Skipping WPBL game without a complete date and time: "
                f"{record.get('id', 'unknown')}",
                file=sys.stderr,
            )
            continue

        local_start = datetime.strptime(
            f"{game_date} {game_time}",
            "%Y%m%d %H:%M:%S",
        ).replace(tzinfo=ZoneInfo(timezone_name))
        start_time = local_start.astimezone(timezone.utc)
        end_time = start_time + timedelta(hours=3)

        title_record = record.get("title", {})
        title = html.unescape(
            str(title_record.get("rendered", "Untitled WPBL game"))
        )
        game_status = str(
            wpbl_acf_value(record, "game_status") or "scheduled"
        ).lower()
        status = {
            "cancelled": "CANCELLED",
            "postponed": "TENTATIVE",
        }.get(game_status, "CONFIRMED")
        source_uid = f"wpbl-game-{record['id']}"
        link = str(record.get("link", ""))

        collected_events.append(
            SportsEvent(
                event_id=create_event_id(
                    source_id=calendar_source.source_id,
                    source_uid=source_uid,
                    recurrence_id="",
                    title=title,
                    start_time_utc=start_time,
                ),
                source_id=calendar_source.source_id,
                source_uid=source_uid,
                sport=calendar_source.sport,
                competition=calendar_source.competition,
                title=title,
                start_time_utc=start_time.isoformat(),
                end_time_utc=end_time.isoformat(),
                location=(
                    "Robin Roberts Stadium, Springfield, Illinois"
                ),
                description=(
                    f"WPBL game. Schedule status: {game_status}."
                ),
                official_url=link,
                status=status,
                source_url=calendar_source.source,
                last_checked_utc=checked_at,
            )
        )

    return collected_events


WSL_COMPETITION_ID = "e32284e8a1214f1ca83a3245d690b336"


def parse_wsl_fixture_page(
    page_html: str,
    calendar_source: CalendarSource,
) -> list[SportsEvent]:
    """Parse the complete Barclays WSL dataset embedded in its page."""
    checked_at = datetime.now(timezone.utc).isoformat()
    london_timezone = ZoneInfo("Europe/London")
    collected_events: list[SportsEvent] = []
    next_data_blocks: list[str] = []

    for raw_value in re.findall(
        r"self\.__next_f\.push\((\[.*?\])\)</script>",
        page_html,
        re.DOTALL,
    ):
        try:
            value = json.loads(raw_value)
        except json.JSONDecodeError:
            continue

        if len(value) > 1 and isinstance(value[1], str):
            next_data_blocks.append(value[1])

    next_data = "".join(next_data_blocks)
    marker = '"initialMatches":'

    if marker not in next_data:
        raise ValueError(
            "The official WSL page did not contain its fixture dataset."
        )

    match_data = json.JSONDecoder().raw_decode(
        next_data.split(marker, 1)[1]
    )[0]

    for match in match_data:
        competition_id = str(
            (match.get("matchSet") or {}).get("competitionId", "")
        )

        if not competition_id.endswith(WSL_COMPETITION_ID):
            continue

        raw_match_id = str(match.get("matchId", ""))
        match_id = raw_match_id.rsplit("::", 1)[-1]
        home = match.get("home") or {}
        away = match.get("away") or {}
        home_team = str(
            home.get("mediaName")
            or home.get("officialName")
            or home.get("shortName")
            or "Home team"
        )
        away_team = str(
            away.get("mediaName")
            or away.get("officialName")
            or away.get("shortName")
            or "Away team"
        )
        kickoff_unknown = bool(match.get("isUnknownKickOffTime"))
        raw_start = str(match.get("matchDateUtc", ""))

        if not match_id or not raw_start:
            print(
                "Skipping WSL fixture without a match ID or date.",
                file=sys.stderr,
            )
            continue

        if kickoff_unknown:
            fixture_date = date.fromisoformat(raw_start[:10])
            local_start = datetime.combine(fixture_date, time(hour=12))
            local_start = local_start.replace(tzinfo=london_timezone)
            start_time = local_start.astimezone(timezone.utc)
        else:
            start_time = datetime.fromisoformat(
                raw_start.replace("Z", "+00:00")
            ).astimezone(timezone.utc)

        end_time = start_time + timedelta(hours=2)
        title = f"{home_team} vs. {away_team}"
        source_uid = f"wsl-match-{match_id}"
        provider_status = str(match.get("status", "UPCOMING")).upper()
        status = {
            "CANCELED": "CANCELLED",
            "CANCELLED": "CANCELLED",
            "POSTPONED": "TENTATIVE",
            "SUSPENDED": "TENTATIVE",
        }.get(provider_status, "CONFIRMED")

        if kickoff_unknown:
            status = "TENTATIVE"

        description = "Official Barclays WSL fixture."

        if kickoff_unknown:
            description += " Kickoff time is to be confirmed."

        collected_events.append(
            SportsEvent(
                event_id=create_event_id(
                    source_id=calendar_source.source_id,
                    source_uid=source_uid,
                    recurrence_id="",
                    title=title,
                    start_time_utc=start_time,
                ),
                source_id=calendar_source.source_id,
                source_uid=source_uid,
                sport=calendar_source.sport,
                competition=calendar_source.competition,
                title=title,
                start_time_utc=start_time.isoformat(),
                end_time_utc=end_time.isoformat(),
                location=str(match.get("stadiumName") or ""),
                description=description,
                official_url=str(match.get("matchUrl") or ""),
                status=status,
                source_url=calendar_source.source,
                last_checked_utc=checked_at,
            )
        )

    if not collected_events:
        raise ValueError(
            "The official WSL fixtures page returned no Barclays WSL "
            "matches. Its markup may have changed."
        )

    return collected_events


def collect_wsl_events(
    calendar_source: CalendarSource,
) -> list[SportsEvent]:
    """Collect fixtures from the official WSL Football website."""
    response = requests.get(
        calendar_source.source,
        timeout=30,
        headers={
            "User-Agent": (
                "HerMatchCalendarBot/0.4 "
                "(women's sports calendar)"
            )
        },
    )
    response.raise_for_status()
    return parse_wsl_fixture_page(response.text, calendar_source)


def collect_source_events(
    calendar_source: CalendarSource,
) -> list[SportsEvent]:
    if calendar_source.source_type == "wpbl_api":
        return collect_wpbl_events(calendar_source)

    if calendar_source.source_type == "wsl_official":
        return collect_wsl_events(calendar_source)

    return collect_ics_events(calendar_source)


def load_existing_events() -> dict[str, SportsEvent]:
    """
    Load the existing event database.

    Older CSV files that predate source_id are accepted. Their source_id
    is left blank, and those records disappear when the current source
    snapshot is saved.
    """
    if not EVENTS_FILE.exists():
        return {}

    existing_events: dict[str, SportsEvent] = {}
    field_names = {
        field.name for field in fields(SportsEvent)
    }

    with EVENTS_FILE.open(
        "r",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        reader = csv.DictReader(file)

        for row in reader:
            normalized_row = {
                field_name: row.get(field_name, "")
                for field_name in field_names
            }

            event = SportsEvent(**normalized_row)
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


def reconcile_events(
    existing_events: dict[str, SportsEvent],
    collected_events: list[SportsEvent],
) -> tuple[dict[str, SportsEvent], list[dict[str, str]]]:
    """
    Compare the previous database with the current source snapshot.

    The returned database contains only events currently supplied by the
    enabled sources. This prevents removed feeds and old test records from
    continuing to appear in the newsletter.
    """
    current_events = {
        event.event_id: event
        for event in collected_events
    }
    changes: list[dict[str, str]] = []
    detected_at = datetime.now(timezone.utc).isoformat()

    for event_id, new_event in current_events.items():
        old_event = existing_events.get(event_id)

        if old_event is None:
            changes.append(
                {
                    "detected_at_utc": detected_at,
                    "event_id": new_event.event_id,
                    "source_id": new_event.source_id,
                    "title": new_event.title,
                    "competition": new_event.competition,
                    "change_type": "new_event",
                    "changed_fields": "",
                }
            )
            continue

        changed_fields = compare_events(
            old_event,
            new_event,
        )

        if changed_fields:
            changes.append(
                {
                    "detected_at_utc": detected_at,
                    "event_id": new_event.event_id,
                    "source_id": new_event.source_id,
                    "title": new_event.title,
                    "competition": new_event.competition,
                    "change_type": "updated_event",
                    "changed_fields": ",".join(changed_fields),
                }
            )

    for event_id, old_event in existing_events.items():
        if event_id not in current_events:
            changes.append(
                {
                    "detected_at_utc": detected_at,
                    "event_id": old_event.event_id,
                    "source_id": old_event.source_id,
                    "title": old_event.title,
                    "competition": old_event.competition,
                    "change_type": "removed_event",
                    "changed_fields": "",
                }
            )

    return current_events, changes


def save_events(events: dict[str, SportsEvent]) -> None:
    field_names = [
        field.name for field in fields(SportsEvent)
    ]

    ordered_events = sorted(
        events.values(),
        key=lambda event: (
            event.start_time_utc,
            event.sport,
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
            lineterminator="\n",
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
        "source_id",
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


def format_local_time(value: datetime) -> str:
    """
    Format a time without relying on the Unix-only %-I directive.
    """
    return value.strftime("%I:%M %p").lstrip("0")


def generate_newsletter(
    events: dict[str, SportsEvent],
    timezone_name: str,
    days_ahead: int,
) -> int:
    """
    Generate Markdown grouped by league.

    Each match uses this format:

    ### Team A vs Team B

    Saturday, July 18 | 2:00 PM | Stadium name
    """
    local_timezone = ZoneInfo(timezone_name)
    now_local = datetime.now(local_timezone)
    date_limit = now_local + timedelta(days=days_ahead)

    upcoming_events: list[
        tuple[datetime, SportsEvent]
    ] = []

    for event in events.values():
        if event.status.upper() == "CANCELLED":
            continue

        start_utc = datetime.fromisoformat(
            event.start_time_utc
        )

        if start_utc.tzinfo is None:
            start_utc = start_utc.replace(
                tzinfo=timezone.utc
            )

        start_local = start_utc.astimezone(
            local_timezone
        )

        if now_local <= start_local < date_limit:
            upcoming_events.append(
                (start_local, event)
            )

    upcoming_events.sort(
        key=lambda item: (
            item[1].competition.casefold(),
            item[0],
            item[1].title.casefold(),
        )
    )

    grouped_events: dict[
        str,
        list[tuple[datetime, SportsEvent]],
    ] = {}

    for local_start, event in upcoming_events:
        grouped_events.setdefault(
            event.competition,
            [],
        ).append((local_start, event))

    lines: list[str] = []

    for competition, competition_events in grouped_events.items():
        if lines:
            lines.append("")

        lines.extend(
            [
                f"## {competition}",
                "",
            ]
        )

        for local_start, event in competition_events:
            match_details = (
                f"{local_start.strftime('%A, %B %d')} "
                f"| {format_local_time(local_start)} "
                f"| {event.location or 'Location TBD'}"
            )

            lines.extend(
                [
                    f"### {event.title}",
                    "",
                    match_details,
                    "",
                ]
            )

            if event.official_url:
                lines.extend(
                    [
                        (
                            "[Official match information]"
                            f"({event.official_url})"
                        ),
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
        "\n".join(lines).strip() + "\n",
        encoding="utf-8",
    )

    return len(upcoming_events)


def main() -> None:
    load_dotenv()
    ensure_directories()

    calendar_sources = load_calendar_sources()

    timezone_name = os.getenv(
        "DISPLAY_TIMEZONE",
        "America/Toronto",
    ).strip()

    try:
        days_ahead = int(
            os.getenv("DAYS_AHEAD", "7")
        )
    except ValueError as exc:
        raise ValueError(
            "DAYS_AHEAD must be a whole number."
        ) from exc

    if days_ahead <= 0:
        raise ValueError(
            "DAYS_AHEAD must be greater than zero."
        )

    collected_events: list[SportsEvent] = []

    for calendar_source in calendar_sources:
        print(
            "Collecting events from "
            f"{calendar_source.competition}..."
        )

        source_events = collect_source_events(
            calendar_source
        )
        collected_events.extend(source_events)

        print(
            f"  Collected {len(source_events)} event(s)."
        )

    existing_events = load_existing_events()

    current_events, changes = reconcile_events(
        existing_events=existing_events,
        collected_events=collected_events,
    )

    save_events(current_events)
    append_changes(changes)

    newsletter_count = generate_newsletter(
        events=current_events,
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
    removed_event_count = sum(
        change["change_type"] == "removed_event"
        for change in changes
    )

    print(f"Sources: {len(calendar_sources)}")
    print(f"Collected: {len(collected_events)}")
    print(f"New events: {new_event_count}")
    print(f"Updated events: {updated_event_count}")
    print(f"Removed events: {removed_event_count}")
    print(f"Newsletter events: {newsletter_count}")
    print(f"Event database: {EVENTS_FILE}")
    print(f"Change log: {CHANGES_FILE}")
    print(f"Newsletter draft: {NEWSLETTER_FILE}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(
            f"Automation failed: {error}",
            file=sys.stderr,
        )
        raise
