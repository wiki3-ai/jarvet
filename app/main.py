from __future__ import annotations

import json
import os
import re
from contextlib import asynccontextmanager
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.agent import run_agent
from app.onet import OnetGraph
from app.va import VaComparison

ROOT = Path(__file__).resolve().parent.parent
index = OnetGraph(ROOT / ".cache" / "onet-store")
va_index = VaComparison(ROOT / ".cache" / "va-comparison.sqlite")


@asynccontextmanager
async def lifespan(_: FastAPI):
    index.load()
    va_index.load()
    yield


app = FastAPI(title="Jarvet", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=ROOT / "app" / "static"), name="static")


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[Message] = Field(min_length=1, max_length=30)
    profile: dict[str, list[str]] = Field(default_factory=dict)
    selected_occupation: dict[str, str] | None = None


PROFILE_FIELDS = (
    "interests", "strengths", "goals", "preferences", "constraints", "education",
    "location", "notes",
)

VA_RESOURCES = {
    "compare": {"label": "Search approved schools and employers", "url": "https://www.va.gov/education/gi-bill-comparison-tool/"},
    "eligibility": {"label": "Check education benefit eligibility", "url": "https://www.va.gov/education/eligibility/"},
    "remaining": {"label": "Check remaining GI Bill benefits", "url": "https://www.va.gov/education/check-remaining-post-9-11-gi-bill-benefits/"},
    "other": {"label": "Explore other VA education benefits", "url": "https://www.va.gov/education/other-va-education-benefits/"},
    "ojt": {"label": "Learn about OJT and apprenticeships", "url": "https://www.va.gov/education/about-gi-bill-benefits/how-to-use-benefits/on-the-job-training-apprenticeships/"},
    "apprenticeship": {"label": "Search open apprenticeship opportunities", "url": "https://www.apprenticeship.gov/apprenticeship-job-finder"},
    "vocational": {"label": "Learn about non-college programs", "url": "https://www.va.gov/education/about-gi-bill-benefits/how-to-use-benefits/non-college-degree-programs/"},
    "vre": {"label": "Explore Veteran Readiness and Employment", "url": "https://www.va.gov/careers-employment/vocational-rehabilitation/"},
    "bright": {"label": "Browse all Bright Outlook occupations", "url": "https://www.onetonline.org/find/bright?b=0"},
}


class TrainingTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.programs: list[dict[str, str]] = []
        self.row: dict[str, str] | None = None
        self.field = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "tr":
            self.row = {}
        elif tag == "td" and self.row is not None:
            self.field = (attributes.get("data-title") or "").lower().replace(" ", "_")
            if self.field == "school" and attributes.get("data-text"):
                self.row["school"] = attributes["data-text"] or ""
            if self.field == "recent_graduates" and attributes.get("data-text"):
                self.row["recent_graduates"] = attributes["data-text"] or ""
        elif tag == "a" and self.row is not None and self.field == "school":
            href = attributes.get("href") or ""
            if href.startswith(("http://", "https://")) and "mynextmove.org" not in href:
                self.row.setdefault("url", href)

    def handle_endtag(self, tag: str) -> None:
        if tag == "td":
            self.field = ""
        elif tag == "tr" and self.row is not None:
            if self.row.get("program") and self.row.get("school"):
                self.row["program"] = " ".join(self.row["program"].split())
                self.programs.append(self.row)
            self.row = None

    def handle_data(self, data: str) -> None:
        if self.row is not None and self.field == "program":
            self.row["program"] = self.row.get("program", "") + data


async def fetch_local_training(code: str, zip_code: str) -> list[dict[str, str]] | None:
    if not zip_code:
        return []
    url = f"https://www.mynextmove.org/vets/profile/localtraining/{code}?zip={zip_code}"
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
    except httpx.HTTPError:
        return None
    parser = TrainingTableParser()
    parser.feed(response.text)
    return parser.programs[:8]


def clean_profile(raw: Any, fallback: dict[str, list[str]]) -> dict[str, list[str]]:
    if not isinstance(raw, dict):
        return fallback
    profile: dict[str, list[str]] = {}
    for field in PROFILE_FIELDS:
        values = raw.get(field, fallback.get(field, []))
        if isinstance(values, list):
            profile[field] = [str(value).strip() for value in values if str(value).strip()][:8]
    accepted: list[set[str]] = []
    for field, value in sorted(
        ((field, value) for field, values in profile.items() for value in values),
        key=lambda item: len(item[1]),
    ):
        tokens = set(re.findall(r"[a-z0-9]+", value.lower()))
        if any(
            tokens == existing
            or min(len(tokens), len(existing)) >= 3
            and len(tokens & existing) / min(len(tokens), len(existing)) >= 0.8
            for existing in accepted
        ):
            profile[field].remove(value)
        else:
            accepted.append(tokens)
    return profile


def parse_turn(content: str, profile: dict[str, list[str]]) -> dict[str, Any]:
    candidate = content.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", candidate, re.DOTALL)
    if fenced:
        candidate = fenced.group(1)
    elif not candidate.startswith("{"):
        object_start = candidate.rfind('{"message"')
        if object_start >= 0:
            candidate = candidate[object_start:]
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return {"message": content, "suggestions": [], "profile": profile}

    suggestions = []
    for item in parsed.get("suggestions", []):
        if not isinstance(item, dict):
            continue
        label = str(item.get("label", "")).strip()
        value = str(item.get("value", label)).strip()
        if label and value:
            suggestions.append({"label": label[:48], "value": value[:240]})
    message = str(parsed.get("message", "")).strip() or content
    message = re.sub(r"\*\*(.+?)\*\*", r"\1", message)
    message = re.sub(r"(?m)^\s*[-*]\s+", "- ", message)
    return {
        "message": message,
        "suggestions": suggestions[:4],
        "profile": clean_profile(parsed.get("profile"), profile),
    }


def retain_explicit_context(
    previous: dict[str, list[str]], updated: dict[str, list[str]], user_message: str,
) -> dict[str, list[str]]:
    if updated != previous or not re.search(r"\b(i|i'm|i'd|my|me)\b", user_message, re.I):
        return updated
    result = {field: list(values) for field, values in updated.items()}
    notes = result.setdefault("notes", [])
    note = user_message.strip()
    if note and note not in notes:
        notes.append(note[:240])
    return result


@app.get("/")
def home():
    return FileResponse(ROOT / "app" / "static" / "index.html")


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "occupations": index.occupation_count,
        "va_facilities": va_index.facility_count,
        "query_engine": "Oxigraph",
        "agent": "native-tool-calling",
        "model": os.getenv("LLM_MODEL", ""),
    }


@app.post("/api/chat")
async def chat(request: ChatRequest):
    profile = clean_profile(request.profile, {})
    base_url = os.getenv("LLM_BASE_URL", "http://host.docker.internal:8888/v1").rstrip("/")
    api_key = os.getenv("LLM_API_KEY", "")
    model = os.getenv("LLM_MODEL", "")
    if not api_key:
        raise HTTPException(503, "LLM_API_KEY is not configured in the container environment.")
    try:
        result = await run_agent(
            messages=[message.model_dump() for message in request.messages],
            profile=profile,
            selected_occupation=request.selected_occupation,
            onet=index,
            va=va_index,
            fetch_training=fetch_local_training,
            official_resources=VA_RESOURCES,
            base_url=base_url,
            api_key=api_key,
            model=model,
        )
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as error:
        raise HTTPException(502, f"The language model agent failed: {error}") from error

    turn = parse_turn(result["content"], profile)
    turn["profile"] = retain_explicit_context(
        profile, turn["profile"], request.messages[-1].content,
    )
    location = result.get("resolved_location")
    if location:
        normalized_label = re.sub(r"[^a-z0-9]+", " ", location["label"].lower()).strip()
        turn["profile"]["location"] = [
            value for value in turn["profile"].setdefault("location", [])
            if re.sub(r"[^a-z0-9]+", " ", value.lower()).strip() != normalized_label
        ]
        turn["profile"]["location"].append(location["label"])
    return {
        **turn,
        "resources": result["resources"],
        "matches": result["matches"][:3],
        "selected_occupation": result["selected_occupation"],
    }
