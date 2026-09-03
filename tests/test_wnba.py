import unittest
from unittest.mock import Mock, patch

from main import (
    CalendarSource,
    load_wnba_schedule,
    parse_wnba_schedule,
    wnba_season_from_source,
)


SOURCE = CalendarSource(
    source_id="wnba",
    source="https://www.wnba.com/schedule?month=all&season=2026",
    sport="Basketball",
    competition="WNBA",
    source_type="wnba_official",
)


class WnbaCollectorTests(unittest.TestCase):
    def test_reads_season_from_source_url(self):
        self.assertEqual(wnba_season_from_source(SOURCE.source), "2026")

    def test_rejects_source_without_valid_season(self):
        with self.assertRaisesRegex(ValueError, "four-digit season"):
            wnba_season_from_source("https://www.wnba.com/schedule")

    @patch("main.requests.get")
    def test_loads_official_api_for_configured_season(self, get):
        response = Mock()
        response.json.return_value = {"leagueSchedule": {"gameDates": []}}
        get.return_value = response

        result = load_wnba_schedule(SOURCE.source)

        self.assertIn("leagueSchedule", result)
        get.assert_called_once_with(
            "https://www.wnba.com/api/schedule",
            params={"season": "2026", "regionId": "1"},
            timeout=30,
            headers={
                "Accept": "application/json",
                "User-Agent": (
                    "HerMatchCalendarBot/0.5 "
                    "(women's sports calendar)"
                ),
            },
        )
        response.raise_for_status.assert_called_once_with()

    def test_parses_scheduled_game(self):
        payload = {
            "leagueSchedule": {
                "gameDates": [
                    {
                        "games": [
                            {
                                "gameId": "1022600001",
                                "seasonType": "Regular Season",
                                "gameStatus": 1,
                                "gameStatusText": "7:30 pm ET",
                                "gameDateTimeUTC": "2026-05-08T23:30:00Z",
                                "actualEndTimeUTC": "",
                                "postponedStatus": "N",
                                "arenaName": "Barclays Center",
                                "arenaCity": "Brooklyn",
                                "arenaState": "NY",
                                "awayTeam": {
                                    "teamCity": "Connecticut",
                                    "teamName": "Sun",
                                },
                                "homeTeam": {
                                    "teamCity": "New York",
                                    "teamName": "Liberty",
                                },
                            }
                        ]
                    }
                ]
            }
        }

        events = parse_wnba_schedule(payload, SOURCE)

        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event.source_uid, "wnba-game-1022600001")
        self.assertEqual(event.title, "Connecticut Sun vs. New York Liberty")
        self.assertEqual(event.start_time_utc, "2026-05-08T23:30:00+00:00")
        self.assertEqual(event.end_time_utc, "2026-05-09T02:00:00+00:00")
        self.assertEqual(event.location, "Barclays Center, Brooklyn, NY")
        self.assertEqual(event.status, "CONFIRMED")

    def test_maps_postponed_game_to_tentative(self):
        payload = {
            "leagueSchedule": {
                "gameDates": [
                    {
                        "games": [
                            {
                                "gameId": "1022600002",
                                "gameStatusText": "Postponed",
                                "gameDateTimeUTC": "2026-05-09T00:00:00Z",
                                "postponedStatus": "Y",
                                "awayTeam": {"teamName": "Away"},
                                "homeTeam": {"teamName": "Home"},
                            }
                        ]
                    }
                ]
            }
        }

        self.assertEqual(parse_wnba_schedule(payload, SOURCE)[0].status, "TENTATIVE")


if __name__ == "__main__":
    unittest.main()
