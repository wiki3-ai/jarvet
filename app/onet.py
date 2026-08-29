from __future__ import annotations

import csv
import re
import sqlite3
from pathlib import Path
from typing import Any

from pyoxigraph import Store

SCHEMA = "https://www.onetcenter.org/rdf/schema/onet/"
ROOT = Path(__file__).resolve().parent.parent
BRIGHT_OUTLOOK = ROOT / "data" / "db_31_0_nt" / "BrightOutlook.csv"
PREFIXES = f"PREFIX onet: <{SCHEMA}>\nPREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>"
STOP_WORDS = {
    "about", "already", "and", "are", "area", "available", "career", "certificate",
    "become", "consider", "could", "degree", "education", "enjoy", "find", "fits", "have", "help", "idea",
    "interested", "into", "jose", "like", "live", "matching", "near", "nearby", "path",
    "paths", "running", "san", "should", "that", "the", "want", "what", "where", "with",
    "would",
}
def _search_terms(query: str) -> list[str]:
    terms = {
        term for term in re.findall(r"[a-z0-9]+", query.lower())
        if len(term) > 2 and term not in STOP_WORDS and not term.isdigit()
    }
    terms.update(term[:-5] for term in tuple(terms) if term.endswith("shops") and len(term) > 7)
    return sorted(terms)


def _text(term: Any) -> str:
    return term.value if term is not None else ""


class OnetGraph:
    def __init__(self, store_path: Path):
        self.store_path = store_path
        self.store: Store | None = None
        self.search_db: sqlite3.Connection | None = None
        self.occupation_count = 0

    def load(self) -> None:
        if not (self.store_path / "READY").exists():
            raise RuntimeError("O*NET graph store is missing. Run scripts/init-onet-store.py.")
        self.store = Store(str(self.store_path / "oxigraph"))
        search_path = self.store_path / "search.sqlite"
        if not search_path.exists():
            self._build_search_index(search_path)
        self.search_db = sqlite3.connect(search_path, check_same_thread=False)
        row = next(iter(self._query(
            "SELECT (COUNT(?occupation) AS ?count) WHERE "
            "{ ?occupation rdf:type onet:Occupation . }"
        )))
        self.occupation_count = int(_text(row["count"]))

    def _query(self, sparql: str):
        if self.store is None:
            raise RuntimeError("O*NET graph store has not been loaded.")
        return self.store.query(f"{PREFIXES}\n{sparql}")

    def search(self, query: str, limit: int = 5) -> list[dict]:
        if self.search_db is None:
            raise RuntimeError("O*NET search index has not been loaded.")
        terms = _search_terms(query)
        if not terms:
            return []
        term_query = " OR ".join(f'"{term}"*' for term in terms)
        all_terms_query = " AND ".join(f'"{term}"*' for term in terms)
        sql = """SELECT occupation_uri, code, title, description,
                        bm25(occupation_search, 0, 0, 12, 9, 3, 5, 2, 2) AS rank
                 FROM occupation_search WHERE occupation_search MATCH ?
                 ORDER BY rank LIMIT ?"""
        rows = list(self.search_db.execute(
            sql, (f"{{title alternate_titles}} : ({all_terms_query})", limit)
        ))
        if len(rows) < limit:
            seen = {row[1] for row in rows}
            rows.extend(
                row for row in self.search_db.execute(
                    sql, (f"{{title alternate_titles}} : ({term_query})", limit * 2)
                )
                if row[1] not in seen
            )
            rows = rows[:limit]
        if len(rows) < limit:
            seen = {row[1] for row in rows}
            rows.extend(
                row for row in self.search_db.execute(sql, (term_query, limit * 2))
                if row[1] not in seen
            )
            rows = rows[:limit]
        results = []
        for row in rows:
            bright = self.search_db.execute(
                "SELECT categories FROM bright_outlook WHERE code = ?", (row[1],)
            ).fetchone()
            results.append({
                "uri": row[0], "code": row[1], "title": row[2], "description": row[3],
                "bright_outlook": bright[0].split("; ") if bright else [],
            })
        return results

    def results(self, query: str, limit: int = 5) -> list[dict]:
        terms = _search_terms(query)
        return [self._features(item, terms) for item in self.search(query, limit)]

    def result_by_code(self, code: str) -> dict | None:
        if self.search_db is None:
            raise RuntimeError("O*NET search index has not been loaded.")
        row = self.search_db.execute(
            "SELECT occupation_uri, code, title, description FROM occupation_search WHERE code = ?",
            (code,),
        ).fetchone()
        if row is None:
            return None
        bright = self.search_db.execute(
            "SELECT categories FROM bright_outlook WHERE code = ?", (code,)
        ).fetchone()
        occupation = {
            "uri": row[0], "code": row[1], "title": row[2], "description": row[3],
            "bright_outlook": bright[0].split("; ") if bright else [],
        }
        return self._features(occupation, [])

    def related_results(self, occupation: dict, limit: int = 8) -> list[dict]:
        rows = self._query(f"""
            SELECT ?code WHERE {{
              <{occupation['uri']}> onet:hasRelatedOccupation ?link .
              ?link onet:refersTo ?related ; onet:relatedIndex ?index .
              ?related onet:onetSOCCode ?code .
            }} ORDER BY ?index LIMIT {limit}
        """)
        return [result for row in rows if (result := self.result_by_code(_text(row["code"])))]

    def _build_search_index(self, path: Path) -> None:
        documents: dict[str, dict[str, Any]] = {}
        for row in self._query("""
            SELECT ?occupation ?code ?title ?description WHERE {
              ?occupation rdf:type onet:Occupation ; onet:onetSOCCode ?code ;
                onet:title ?title ; onet:description ?description .
            }
        """):
            uri = _text(row["occupation"])
            documents[uri] = {
                "uri": uri, "code": _text(row["code"]), "title": _text(row["title"]),
                "description": _text(row["description"]), "alternate_titles": [],
                "tasks": [], "features": [], "software": [],
            }

        text_queries = {
            "alternate_titles": """
                SELECT ?occupation ?text WHERE {
                  { ?occupation onet:hasJobTitle ?resource . ?resource onet:jobTitle ?text . }
                  UNION
                  { ?occupation onet:hasReportedTitle ?resource .
                    ?resource onet:reportedJobTitle ?text . }
                }
            """,
            "tasks": """
                SELECT ?occupation ?text WHERE {
                  ?occupation onet:hasTask ?resource . ?resource onet:task ?text .
                }
            """,
            "features": """
                SELECT DISTINCT ?occupation ?text WHERE {
                  ?occupation onet:hasRating ?rating . ?rating onet:refersTo ?resource .
                  ?resource onet:elementName|onet:categoryDescription|onet:name ?text .
                }
            """,
            "software": """
                SELECT DISTINCT ?occupation ?text WHERE {
                  ?occupation onet:hasSoftware ?link . ?link onet:refersTo ?resource .
                  ?resource onet:workplaceExample ?text .
                }
            """,
        }
        for field, query in text_queries.items():
            for row in self._query(query):
                document = documents.get(_text(row["occupation"]))
                if document is not None:
                    document[field].append(_text(row["text"]))

        connection = sqlite3.connect(path)
        connection.execute("""
            CREATE VIRTUAL TABLE occupation_search USING fts5(
              occupation_uri UNINDEXED, code UNINDEXED, title, alternate_titles,
              description, tasks, features, software, tokenize='porter unicode61'
            )
        """)
        connection.executemany(
            "INSERT INTO occupation_search VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ((
                    document["uri"], document["code"], document["title"],
                    " | ".join(document["alternate_titles"]), document["description"],
                    " | ".join(document["tasks"]), " | ".join(document["features"]),
                    " | ".join(document["software"]),
                )
                for document in documents.values()
            )
        )
        connection.execute(
            "CREATE TABLE bright_outlook (code TEXT PRIMARY KEY, categories TEXT NOT NULL)"
        )
        with BRIGHT_OUTLOOK.open(newline="", encoding="utf-8-sig") as source:
            connection.executemany(
                "INSERT INTO bright_outlook VALUES (?, ?)",
                ((row["Code"], row["Categories"]) for row in csv.DictReader(source)),
            )
        connection.commit()
        connection.close()

    def _features(self, occupation: dict, search_terms: list[str]) -> dict:
        uri = occupation["uri"]
        education = [
            {"level": _text(row["level"]), "share": float(_text(row["share"]))}
            for row in self._query(f"""
                SELECT ?level ?share WHERE {{
                  <{uri}> onet:hasRating ?rating .
                  ?rating rdf:type onet:EducationRating ; onet:refersTo ?category ;
                    onet:dataValue ?share .
                  ?category onet:categoryDescription ?level .
                }} ORDER BY DESC(?share)
            """)
        ]
        all_tasks = [
            _text(row["task"]) for row in self._query(f"""
                SELECT ?task WHERE {{ <{uri}> onet:hasTask ?resource .
                  ?resource onet:task ?task . }}
            """)
        ]
        tasks = sorted(
            all_tasks,
            key=lambda task: sum(
                any(token.startswith(term[:4]) for token in re.findall(r"[a-z0-9]+", task.lower()))
                for term in search_terms
            ),
            reverse=True,
        )[:6]
        software = [
            _text(row["name"]) for row in self._query(f"""
                SELECT DISTINCT ?name WHERE {{ <{uri}> onet:hasSoftware ?link .
                  ?link onet:refersTo ?resource .
                  ?resource onet:workplaceExample ?name . }} LIMIT 8
            """)
        ]
        job_zone_rows = list(self._query(f"""
            SELECT ?name ?education ?experience ?training WHERE {{
              <{uri}> onet:hasRating ?rating .
              ?rating rdf:type onet:JobZoneRating ; onet:refersTo ?zone .
              ?zone onet:name ?name ; onet:education ?education ;
                onet:experience ?experience ; onet:jobTraining ?training .
            }} LIMIT 1
        """))
        job_zone = None
        if job_zone_rows:
            row = job_zone_rows[0]
            job_zone = {key: _text(row[key]) for key in (
                "name", "education", "experience", "training"
            )}
        elements = [
            {
                "name": _text(row["name"]),
                "type": _text(row["type"]).rsplit("/", 1)[-1],
                "score": float(_text(row["score"])),
            }
            for row in self._query(f"""
                SELECT ?name ?type (MAX(?value) AS ?score) WHERE {{
                  <{uri}> onet:hasRating ?rating .
                  ?rating rdf:type ?type ; onet:refersTo ?element ; onet:dataValue ?value .
                  ?element onet:elementName ?name .
                  FILTER(?type IN (onet:EssentialSkillsRating, onet:KnowledgeRating,
                    onet:AbilitiesRating, onet:WorkActivitiesRating, onet:WorkStylesRating))
                }} GROUP BY ?name ?type ORDER BY DESC(?score) LIMIT 12
            """)
        ]
        return {
            **occupation,
            "education": education,
            "tasks": tasks,
            "software": software,
            "job_zone": job_zone,
            "elements": elements,
        }