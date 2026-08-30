from __future__ import annotations

import math
import re
import sqlite3
from pathlib import Path
from typing import Any

STATE_NAMES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "district of columbia": "DC", "florida": "FL", "georgia": "GA", "hawaii": "HI",
    "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI",
    "south carolina": "SC", "south dakota": "SD", "tennessee": "TN", "texas": "TX",
    "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
}


def _normalized(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _distance_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    latitude_delta = math.radians(lat2 - lat1)
    longitude_delta = math.radians(lon2 - lon1)
    start_latitude = math.radians(lat1)
    end_latitude = math.radians(lat2)
    haversine = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(start_latitude) * math.cos(end_latitude) * math.sin(longitude_delta / 2) ** 2
    )
    return 3958.8 * 2 * math.asin(math.sqrt(haversine))


class VaComparison:
    def __init__(self, path: Path):
        self.path = path
        self.connection: sqlite3.Connection | None = None
        self.facility_count = 0
        self.cities: list[tuple[str, str, str]] = []

    def load(self) -> None:
        if not self.path.exists():
            raise RuntimeError("VA Comparison Tool index is missing. Run scripts/init-va-data.py.")
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.facility_count = self.connection.execute(
            "SELECT COUNT(*) FROM facilities"
        ).fetchone()[0]
        self.cities = [
            (row[0], row[1], _normalized(row[0]))
            for row in self.connection.execute(
                "SELECT DISTINCT city, state FROM facilities "
                "WHERE city IS NOT NULL AND state IS NOT NULL"
            )
        ]

    def _database(self) -> sqlite3.Connection:
        if self.connection is None:
            raise RuntimeError("VA Comparison Tool index has not been loaded.")
        return self.connection

    def nearby(
        self, zip_code: str, *, employer: bool | None = None, limit: int = 8,
        max_miles: float = 100,
    ) -> list[dict[str, Any]]:
        database = self._database()
        center = database.execute(
            "SELECT latitude, longitude FROM zcta WHERE zip = ?", (zip_code,)
        ).fetchone()
        if center is None:
            return []
        return self.nearby_coordinates(
            center["latitude"], center["longitude"], employer=employer,
            limit=limit, max_miles=max_miles,
        )

    def nearby_coordinates(
        self, latitude: float, longitude: float, *, employer: bool | None = None,
        limit: int = 8, max_miles: float = 100,
    ) -> list[dict[str, Any]]:
        database = self._database()
        clauses = ["approved = 1", "latitude IS NOT NULL", "longitude IS NOT NULL"]
        if employer is True:
            clauses.append("employer_provider = 1")
        elif employer is False:
            clauses.append("school_provider = 1")
        rows = database.execute(
            "SELECT * FROM facilities WHERE " + " AND ".join(clauses)
        )
        facilities = []
        for row in rows:
            distance = _distance_miles(
                latitude, longitude, row["latitude"], row["longitude"]
            )
            if distance <= max_miles:
                facilities.append(self._record(row, distance))
        return sorted(facilities, key=lambda item: item["distance_miles"])[:limit]

    def resolve_area(self, text: str) -> dict[str, Any] | None:
        normalized = f" {_normalized(text)} "
        state = None
        for name, abbreviation in STATE_NAMES.items():
            if f" {name} " in normalized:
                state = abbreviation
                break
        if state is None:
            abbreviation_match = re.search(r",\s*([A-Za-z]{2})\b", text)
            abbreviation = abbreviation_match.group(1) if abbreviation_match else ""
            if (
                abbreviation.upper() in STATE_NAMES.values()
                and not (abbreviation.islower() and abbreviation.lower() == "me")
            ):
                state = abbreviation.upper()
            else:
                trailing = re.search(r"\b([A-Za-z]{2})\s*$", text)
                candidate = trailing.group(1).upper() if trailing else ""
                if candidate in STATE_NAMES.values() and (
                    text.strip().upper() == candidate
                    or any(
                        city_state == candidate and f" {normalized_city} " in normalized
                        for _, city_state, normalized_city in self.cities
                    )
                ):
                    state = candidate

        city_matches = [
            (city, city_state, normalized_city)
            for city, city_state, normalized_city in self.cities
            if (state is None or city_state == state)
            and f" {normalized_city} " in normalized
        ]
        if city_matches:
            states = {item[1] for item in city_matches}
            if state is None and len(states) != 1:
                return None
            city, state, _ = max(city_matches, key=lambda item: len(item[2]))
            where = "city = ? COLLATE NOCASE AND state = ?"
            parameters = (city, state)
            label = f"{city.title()}, {state}"
        elif state:
            where = "state = ?"
            parameters = (state,)
            label = state
        else:
            return None

        database = self._database()
        representative = database.execute(
            f"SELECT substr(zip, 1, 5), COUNT(*) AS uses FROM facilities WHERE {where} "
            "AND zip GLOB '[0-9][0-9][0-9][0-9][0-9]*' "
            "GROUP BY substr(zip, 1, 5) ORDER BY uses DESC LIMIT 1",
            parameters,
        ).fetchone()
        center = None
        if city_matches and representative:
            center = database.execute(
                "SELECT latitude, longitude FROM zcta WHERE zip = ?", (representative[0],)
            ).fetchone()
        if center is None:
            center = database.execute(
                f"SELECT AVG(latitude), AVG(longitude) FROM facilities WHERE {where} "
                "AND latitude IS NOT NULL AND longitude IS NOT NULL",
                parameters,
            ).fetchone()
        if center is None or center[0] is None or center[1] is None:
            return None
        return {
            "label": label,
            "city": city if city_matches else None,
            "state": state,
            "latitude": center[0],
            "longitude": center[1],
            "representative_zip": representative[0] if representative else "",
        }

    def resolve_location(self, text: str) -> dict[str, Any] | None:
        zip_match = re.search(r"\b(\d{5})(?:-\d{4})?\b", text)
        if not zip_match:
            return self.resolve_area(text)
        zip_code = zip_match.group(1)
        center = self._database().execute(
            "SELECT latitude, longitude FROM zcta WHERE zip = ?", (zip_code,)
        ).fetchone()
        if center is None:
            return None
        return {
            "label": zip_code,
            "city": None,
            "state": None,
            "latitude": center["latitude"],
            "longitude": center["longitude"],
            "representative_zip": zip_code,
        }

    def search_nearby(
        self, latitude: float, longitude: float, keywords: list[str], *,
        employer: bool | None = None, limit: int = 8, max_miles: float = 100,
    ) -> list[dict[str, Any]]:
        terms = [_normalized(keyword) for keyword in keywords if _normalized(keyword)]
        if not terms:
            return []
        clauses = ["approved = 1", "latitude IS NOT NULL", "longitude IS NOT NULL"]
        if employer is True:
            clauses.append("employer_provider = 1")
        elif employer is False:
            clauses.append("school_provider = 1")
        rows = self._database().execute(
            "SELECT * FROM facilities WHERE " + " AND ".join(clauses)
        )
        facilities = []
        for row in rows:
            name = _normalized(row["institution"])
            if not any(term in name for term in terms):
                continue
            distance = _distance_miles(latitude, longitude, row["latitude"], row["longitude"])
            if distance <= max_miles:
                facilities.append(self._record(row, distance))
        return sorted(facilities, key=lambda item: item["distance_miles"])[:limit]

    def match_school(self, name: str) -> dict[str, Any] | None:
        normalized = re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()
        rows = self._database().execute(
            "SELECT * FROM facilities WHERE approved = 1 AND school_provider = 1"
        )
        best = None
        for row in rows:
            candidate = re.sub(r"[^a-z0-9]+", " ", row["institution"].lower()).strip()
            if candidate == normalized:
                return self._record(row)
            if normalized in candidate or candidate in normalized:
                best = self._record(row)
        return best

    @staticmethod
    def _record(row: sqlite3.Row, distance: float | None = None) -> dict[str, Any]:
        return {
            "facility_code": row["facility_code"],
            "detail_url": (
                "https://www.va.gov/education/gi-bill-comparison-tool/"
                "schools-and-employers/institution/"
                + row["facility_code"]
            ),
            "institution": row["institution"],
            "city": row["city"],
            "state": row["state"],
            "zip": row["zip"],
            "type": row["type"],
            "distance_miles": round(distance, 1) if distance is not None else None,
            "monthly_housing_rate": _number(row["bah"]),
            "website": row["insturl"],
            "veteran_tuition_policy_url": row["vet_tuition_policy_url"],
            "p911_recipients": row["p911_recipients"],
            "p911_tuition_fees": _number(row["p911_tuition_fees"]),
            "yellow_ribbon_recipients": row["p911_yr_recipients"],
            "yellow_ribbon_payments": _number(row["p911_yellow_ribbon"]),
            "accredited": bool(row["accredited"]),
            "accreditation_status": row["accreditation_status"],
            "caution_flag": bool(row["caution_flag"]),
            "caution_flag_reason": row["caution_flag_reason"],
            "school_closing": bool(row["school_closing"]),
            "credit_for_military_training": bool(row["credit_for_mil_training"]),
        }

    def find_facility(self, query: str) -> dict[str, Any] | None:
        normalized = _normalized(query)
        if not normalized:
            return None
        exact_code = self._database().execute(
            "SELECT * FROM facilities WHERE facility_code = ? COLLATE NOCASE AND approved = 1",
            (query.strip(),),
        ).fetchone()
        if exact_code:
            return self._record(exact_code)
        rows = self._database().execute("SELECT * FROM facilities WHERE approved = 1")
        best = None
        best_score = 0.0
        query_terms = set(normalized.split())
        for row in rows:
            name = _normalized(row["institution"])
            if name == normalized:
                return self._record(row)
            name_terms = set(name.split())
            score = len(query_terms & name_terms) / max(len(query_terms), 1)
            if score > best_score and (normalized in name or score >= 0.75):
                best = row
                best_score = score
        return self._record(best) if best is not None else None
