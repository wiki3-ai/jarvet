from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.onet import OnetIndex

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / os.getenv("ONET_DATASET", "db_31_0_nt")
index = OnetIndex(DATA_DIR, ROOT / ".cache" / "onet-index.json")


@asynccontextmanager
async def lifespan(_: FastAPI):
    index.load()
    yield


app = FastAPI(title="Jarvet", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=ROOT / "app" / "static"), name="static")


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[Message] = Field(min_length=1, max_length=30)


@app.get("/")
def home():
    return FileResponse(ROOT / "app" / "static" / "index.html")


@app.get("/api/health")
def health():
    return {"status": "ok", "occupations": len(index.occupations)}


@app.post("/api/chat")
async def chat(request: ChatRequest):
    user_message = request.messages[-1].content.strip()
    matches = index.search(user_message)
    evidence = "\n\n".join(
        f"{item['title']} ({item['code']}): {item['description']}\n"
        + "Education reported by workers: "
        + "; ".join(f"{entry['level']} ({entry['share']:.1f}%)" for entry in item["education"][:4])
        for item in matches
    ) or "No direct occupation match was found. Ask a clarifying question."

    base_url = os.getenv("LLM_BASE_URL", "http://host.docker.internal:8888/v1").rstrip("/")
    api_key = os.getenv("LLM_API_KEY", "")
    model = os.getenv("LLM_MODEL", "")
    if not api_key:
        raise HTTPException(503, "LLM_API_KEY is not configured in the container environment.")

    system = f"""You are Jarvet, an education pathway guide. Help people identify occupations that fit their interests and the education paths commonly associated with those occupations. Be warm, concise, and practical. Respond in plain text without Markdown. Ask one focused question when details are missing. Never invent schools, programs, costs, admissions facts, or credentials. Clearly say that O*NET education percentages describe current workers and are not admission requirements. Use only this retrieved O*NET 31.0 evidence for occupation facts:\n\n{evidence}"""
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}]
        + [message.model_dump() for message in request.messages[-12:]],
        "temperature": 0.35,
        "stream": False,
    }
    if not model:
        payload.pop("model")

    try:
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
            response.raise_for_status()
        answer = response.json()["choices"][0]["message"]["content"]
    except (httpx.HTTPError, KeyError, IndexError) as error:
        raise HTTPException(502, f"The language model request failed: {error}") from error
    return {"message": answer, "matches": matches[:3]}