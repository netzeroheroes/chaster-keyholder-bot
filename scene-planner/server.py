"""Local OpenRouter scene planner. No Chaster, no Cursor login.

  .venv\\Scripts\\python.exe scene-planner\\server.py
  then http://127.0.0.1:8787
"""

from __future__ import annotations

import argparse
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import uvicorn

from planner import catalog, chat, llm_configured

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"

app = FastAPI(title="Scene Planner", version="0.3.0")


class ChatTurn(BaseModel):
    role: str
    content: str


class KitIn(BaseModel):
    toys: str = ""
    kinks: list[str] = Field(default_factory=list)
    limits: str = ""


class SessionIn(BaseModel):
    duration_minutes: int = 30
    focus: str = ""
    orgasm: str = "denied"
    notes: str = ""


class ChatRequest(BaseModel):
    adults_confirmed: bool = False
    kit: KitIn | None = None
    session: SessionIn | None = None
    messages: list[ChatTurn] = Field(default_factory=list)


@app.get("/api/meta")
async def meta() -> dict:
    return {
        **catalog(),
        "llm_configured": llm_configured(),
        "path": "/",
    }


@app.post("/api/chat")
async def chat_endpoint(body: ChatRequest) -> dict:
    if not body.adults_confirmed:
        raise HTTPException(status_code=400, detail="Confirm you are 18+.")
    try:
        return await chat(
            [turn.model_dump() for turn in body.messages],
            kit=body.kit.model_dump() if body.kit else None,
            session=body.session.model_dump() if body.session else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


if STATIC.is_dir():
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    async def index():
        return FileResponse(STATIC / "index.html")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    uvicorn.run(
        "server:app",
        host=args.host,
        port=args.port,
        reload=False,
        app_dir=str(ROOT),
    )


if __name__ == "__main__":
    main()
