from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

TRIPLE = re.compile(r'^<([^>]+)> <([^>]+)> (.+) \.$')
LITERAL = re.compile(r'^"((?:[^"\\]|\\.)*)"(?:\^\^<[^>]+>|@[a-z-]+)?$')
SCHEMA = "https://www.onetcenter.org/rdf/schema/onet/"
STOP_WORDS = {
    "about", "and", "are", "career", "consider", "could", "education", "enjoy",
    "find", "help", "into", "like", "matching", "path", "paths", "should", "that",
    "the", "what", "with", "would",
}
SEARCH_ALIASES = {
    "coding": {"code", "computer", "developer", "program", "programmer", "software"},
    "programming": {"code", "computer", "developer", "program", "programmer", "software"},
}


def _search_terms(query: str) -> set[str]:
    terms = {
        term for term in re.findall(r"[a-z0-9]+", query.lower())
        if len(term) > 2 and term not in STOP_WORDS
    }
    variants = set(terms)
    for term in terms:
        variants.update(SEARCH_ALIASES.get(term, set()))
        if term.endswith("ing") and len(term) > 5:
            variants.add(term[:-3])
        if term.endswith("s") and len(term) > 4:
            variants.add(term[:-1])
    return variants


@dataclass
class Occupation:
    uri: str
    code: str = ""
    title: str = ""
    description: str = ""
    education: list[dict] | None = None


def _value(raw: str) -> str:
    if raw.startswith("<"):
        return raw[1:-1]
    match = LITERAL.match(raw)
    return json.loads(f'"{match.group(1)}"') if match else raw


def _triples(path: Path):
    with path.open(encoding="utf-8") as source:
        for line in source:
            match = TRIPLE.match(line.rstrip())
            if match:
                yield match.group(1), match.group(2), _value(match.group(3))


class OnetIndex:
    def __init__(self, data_dir: Path, cache_path: Path):
        self.data_dir = data_dir
        self.cache_path = cache_path
        self.occupations: list[dict] = []

    def load(self) -> None:
        sources = [self.data_dir / name for name in (
            "Occupation.nt", "EducationCategory.nt", "EducationRating.nt"
        )]
        if not all(path.exists() for path in sources):
            raise RuntimeError("O*NET data is missing. Run scripts/init-onet-data.sh.")
        newest_source = max(path.stat().st_mtime for path in sources)
        if self.cache_path.exists() and self.cache_path.stat().st_mtime >= newest_source:
            self.occupations = json.loads(self.cache_path.read_text())
            return
        self.occupations = self._build()
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self.occupations, separators=(",", ":")))

    def _build(self) -> list[dict]:
        category_data: dict[str, dict] = {}
        for subject, predicate, value in _triples(self.data_dir / "EducationCategory.nt"):
            item = category_data.setdefault(subject, {})
            if predicate.startswith(SCHEMA):
                item[predicate.removeprefix(SCHEMA)] = value

        rating_data: dict[str, dict] = {}
        for subject, predicate, value in _triples(self.data_dir / "EducationRating.nt"):
            if predicate.startswith(SCHEMA):
                rating_data.setdefault(subject, {})[predicate.removeprefix(SCHEMA)] = value

        occupations: dict[str, Occupation] = {}
        rating_owners: dict[str, str] = {}
        fields = {"onetSOCCode": "code", "title": "title", "description": "description"}
        for subject, predicate, value in _triples(self.data_dir / "Occupation.nt"):
            name = predicate.removeprefix(SCHEMA)
            if name in fields:
                setattr(occupations.setdefault(subject, Occupation(subject)), fields[name], value)
            elif name == "hasRating":
                rating_owners[value] = subject

        for rating_uri, rating in rating_data.items():
            owner = rating_owners.get(rating_uri)
            category = category_data.get(rating.get("refersTo", ""))
            if owner and category and "dataValue" in rating:
                occupation = occupations.setdefault(owner, Occupation(owner))
                occupation.education = occupation.education or []
                occupation.education.append({
                    "level": category.get("categoryDescription", "Unknown"),
                    "share": float(rating["dataValue"]),
                })

        result = []
        for occupation in occupations.values():
            if occupation.title and occupation.education:
                occupation.education.sort(key=lambda item: item["share"], reverse=True)
                result.append(asdict(occupation))
        return result

    def search(self, query: str, limit: int = 5) -> list[dict]:
        terms = _search_terms(query)
        ranked = []
        for occupation in self.occupations:
            title = occupation["title"].lower()
            description = occupation["description"].lower()
            score = sum(5 for term in terms if term in title) + sum(
                1 for term in terms if term in description
            )
            if score:
                ranked.append((score, occupation["title"], occupation))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        return [item[2] for item in ranked[:limit]]