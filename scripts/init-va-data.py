from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = ROOT / "data" / "va-comparison"
WORKBOOK = SOURCE_DIR / "ComparisonToolData.xlsx"
ZCTA_ARCHIVE = SOURCE_DIR / "2025_Gaz_zcta_national.zip"
DATABASE = ROOT / ".cache" / "va-comparison.sqlite"
MARKER = ROOT / ".cache" / "va-comparison.ready"
INDEX_VERSION = 1
XML_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
FIELDS = (
    "facility code", "institution", "city", "state", "zip", "country", "type",
    "approved", "bah", "insturl", "vet tuition policy url", "pred degree awarded",
    "gibill", "undergrad enrollment", "student veteran", "credit for mil training",
    "p911 tuition fees", "p911 recipients", "p911 yellow ribbon", "p911 yr recipients",
    "accredited", "accreditation type", "accreditation status", "caution flag",
    "caution flag reason", "school closing", "latitude", "longitude",
    "employer provider", "school provider", "ownership name",
)
REAL_FIELDS = {"bah", "p911 tuition fees", "p911 yellow ribbon", "latitude", "longitude"}
INTEGER_FIELDS = {
    "approved", "gibill", "undergrad enrollment", "student veteran",
    "credit for mil training", "p911 recipients", "p911 yr recipients", "accredited",
    "caution flag", "school closing", "employer provider", "school provider",
}


def column_index(reference: str) -> int:
    index = 0
    for character in re.match(r"[A-Z]+", reference).group():
        index = index * 26 + ord(character) - 64
    return index - 1


def shared_strings(archive: ZipFile) -> list[str]:
    values: list[str] = []
    for _, element in ET.iterparse(archive.open("xl/sharedStrings.xml"), events=("end",)):
        if element.tag == XML_NS + "si":
            values.append("".join(node.text or "" for node in element.iter(XML_NS + "t")))
            element.clear()
    return values


def cells(element: ET.Element, strings: list[str]) -> dict[int, str]:
    values: dict[int, str] = {}
    for cell in element.findall(XML_NS + "c"):
        value = cell.find(XML_NS + "v")
        text = "" if value is None else value.text or ""
        if cell.attrib.get("t") == "s" and text:
            text = strings[int(text)]
        values[column_index(cell.attrib["r"])] = text.strip()
    return values


def as_float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_database() -> None:
    if not WORKBOOK.exists() or not ZCTA_ARCHIVE.exists():
        raise SystemExit("VA Comparison Tool or Census ZCTA data is missing. Run init-onet-data.sh.")
    marker = (
        f"{INDEX_VERSION}:{WORKBOOK.stat().st_size}:{WORKBOOK.stat().st_mtime_ns}:"
        f"{ZCTA_ARCHIVE.stat().st_size}:{ZCTA_ARCHIVE.stat().st_mtime_ns}"
    )
    if DATABASE.exists() and MARKER.exists() and MARKER.read_text() == marker:
        print("VA Comparison Tool index is ready.")
        return

    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    DATABASE.unlink(missing_ok=True)
    connection = sqlite3.connect(DATABASE)
    connection.execute("""
        CREATE TABLE facilities (
          facility_code TEXT PRIMARY KEY, institution TEXT NOT NULL, city TEXT, state TEXT,
          zip TEXT, country TEXT, type TEXT, approved INTEGER, bah REAL, insturl TEXT,
          vet_tuition_policy_url TEXT, pred_degree_awarded TEXT, gibill INTEGER,
          undergrad_enrollment INTEGER, student_veteran INTEGER, credit_for_mil_training INTEGER,
          p911_tuition_fees REAL, p911_recipients INTEGER, p911_yellow_ribbon REAL,
          p911_yr_recipients INTEGER, accredited INTEGER, accreditation_type TEXT,
          accreditation_status TEXT, caution_flag INTEGER, caution_flag_reason TEXT,
          school_closing INTEGER, latitude REAL, longitude REAL, employer_provider INTEGER,
          school_provider INTEGER, ownership_name TEXT
        )
    """)
    connection.execute("CREATE INDEX facilities_location ON facilities(latitude, longitude)")
    connection.execute("CREATE INDEX facilities_name ON facilities(institution COLLATE NOCASE)")

    with ZipFile(WORKBOOK) as archive:
        strings = shared_strings(archive)
        header: dict[str, int] = {}
        records = []
        for _, row in ET.iterparse(
            archive.open("xl/worksheets/sheet3.xml"), events=("end",)
        ):
            if row.tag != XML_NS + "row":
                continue
            values = cells(row, strings)
            if not header:
                header = {value.lower(): index for index, value in values.items()}
                missing = set(FIELDS) - set(header)
                if missing:
                    raise RuntimeError(f"VA workbook fields changed: missing {sorted(missing)}")
                row.clear()
                continue
            record = []
            for field in FIELDS:
                value = values.get(header[field], "")
                if field in REAL_FIELDS:
                    value = as_float(value)
                elif field in INTEGER_FIELDS:
                    number = as_float(value)
                    value = round(number) if number is not None else None
                record.append(value if value != "" else None)
            if record[0] and record[1]:
                records.append(record)
            if len(records) >= 1000:
                connection.executemany(
                    "INSERT OR REPLACE INTO facilities VALUES (" + ",".join("?" * len(FIELDS)) + ")",
                    records,
                )
                records.clear()
            row.clear()
        if records:
            connection.executemany(
                "INSERT OR REPLACE INTO facilities VALUES (" + ",".join("?" * len(FIELDS)) + ")",
                records,
            )

    connection.execute("CREATE TABLE zcta (zip TEXT PRIMARY KEY, latitude REAL, longitude REAL)")
    with ZipFile(ZCTA_ARCHIVE) as archive:
        filename = next(name for name in archive.namelist() if name.endswith(".txt"))
        lines = (line.decode("utf-8").strip() for line in archive.open(filename))
        headers = next(lines).split("|")
        zip_column = headers.index("GEOID")
        latitude_column = headers.index("INTPTLAT")
        longitude_column = headers.index("INTPTLONG")
        connection.executemany(
            "INSERT INTO zcta VALUES (?, ?, ?)",
            (
                (fields[zip_column], as_float(fields[latitude_column]), as_float(fields[longitude_column]))
                for line in lines if line and (fields := line.split("|"))
            ),
        )
    connection.commit()
    count = connection.execute("SELECT COUNT(*) FROM facilities").fetchone()[0]
    zip_count = connection.execute("SELECT COUNT(*) FROM zcta").fetchone()[0]
    connection.close()
    MARKER.write_text(marker)
    print(f"Indexed {count:,} VA facilities and {zip_count:,} Census ZIP-area centroids.")


if __name__ == "__main__":
    build_database()
