from __future__ import annotations

import math
import sqlite3
from pathlib import Path
from typing import Any

AWARD_LEVELS = {
    "1": "certificate", "2": "certificate", "3": "associate", "4": "certificate",
    "5": "bachelor's", "6": "post-bachelor's certificate", "7": "master's",
    "8": "post-master's certificate", "17": "doctoral", "18": "doctoral",
    "19": "doctoral", "20": "doctoral", "21": "doctoral",
}
CONTROL_LABELS = {1: "public", 2: "private nonprofit", 3: "private for-profit"}


class IpedsIndex:
    """Local school-program index built from IPEDS completions and the official
    O*NET CIP-to-SOC crosswalk. Replaces scraping My Next Move, which derives
    its local-training table from the same sources."""

    def __init__(self, path: Path):
        self.path = path
        self.connection: sqlite3.Connection | None = None
        self.institution_count = 0
        self.program_count = 0

    def load(self) -> None:
        if not self.path.exists():
            raise RuntimeError("IPEDS index is missing. Run scripts/init-ipeds-data.py.")
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.institution_count = self.connection.execute(
            "SELECT COUNT(*) FROM institutions"
        ).fetchone()[0]
        self.program_count = self.connection.execute(
            "SELECT COUNT(*) FROM programs"
        ).fetchone()[0]

    def _database(self) -> sqlite3.Connection:
        if self.connection is None:
            raise RuntimeError("IPEDS index has not been loaded.")
        return self.connection

    def program_count_for(self, soc_code: str) -> int:
        row = self._database().execute(
            "SELECT program_count FROM soc_index WHERE soc = ?", (soc_code,)
        ).fetchone()
        return row[0] if row else 0

    def programs_for(
        self, soc_code: str, *, latitude: float | None = None,
        longitude: float | None = None, state: str | None = None,
        limit: int = 8,
    ) -> dict[str, Any]:
        """Programs for one O*NET-SOC code, ranked by proximity when
        coordinates are given, otherwise alphabetically. Returns the chosen
        rows plus the total count so the agent can say how many more exist."""
        database = self._database()
        base_sql = (
            "SELECT p.unitid, p.cip, p.awlevel, p.awards, p.soc_codes, "
            "t.title AS cip_title, "
            "i.name, i.city, i.state, i.zip, i.latitude, i.longitude, i.website, "
            "i.control FROM programs p JOIN institutions i ON i.unitid = p.unitid "
            "LEFT JOIN cip_titles t ON t.cip = p.cip "
            "WHERE p.soc_codes LIKE ?"
        )
        pattern = f"%{soc_code}%"
        parameters: list[Any] = [pattern]
        if state:
            base_sql += " AND i.state = ?"
            parameters.append(state.upper())
        rows = database.execute(base_sql, parameters).fetchall()

        scored: list[tuple[float, int, float | None, sqlite3.Row]] = []
        for row in rows:
            socs = row["soc_codes"].split(",")
            if soc_code not in socs:
                continue
            if (
                latitude is not None and longitude is not None
                and row["latitude"] is not None and row["longitude"] is not None
            ):
                distance = _distance_miles(
                    latitude, longitude, row["latitude"], row["longitude"],
                )
                score = -distance
            else:
                distance = None
                score = 0.0
            scored.append((score, -row["awards"], distance, row))
        scored.sort(key=lambda item: (-item[0], item[1]))

        results = []
        for _, _, distance, row in scored[:limit]:
            results.append({
                "unitid": row["unitid"],
                "institution": row["name"],
                "city": row["city"],
                "state": row["state"],
                "zip": row["zip"],
                "cip": row["cip"],
                "cip_title": row["cip_title"] or row["cip"],
                "award_level": AWARD_LEVELS.get(str(row["awlevel"]), "award"),
                "recent_awards": row["awards"],
                "website": row["website"],
                "control": CONTROL_LABELS.get(row["control"]),
                "distance_miles": round(distance, 1) if distance is not None else None,
            })
        return {
            "total": len(scored),
            "programs": results,
            "source": "IPEDS completions + O*NET CIP-to-SOC crosswalk",
        }

    def match_institution(self, name: str) -> dict[str, Any] | None:
        normalized = " ".join(name.lower().split())
        row = self._database().execute(
            "SELECT * FROM institutions WHERE LOWER(name) = ?", (normalized,)
        ).fetchone()
        if row is None:
            return None
        return dict(row)


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
