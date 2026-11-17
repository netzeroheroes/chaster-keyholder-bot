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

from planner import catalog, llm_configured, plan_scene, surprise_brief

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"

app = FastAPI(title="Scene Planner", version="0.1.0")


class PlanRequest(BaseModel):
    adults_confirmed: bool = False
    surprise: bool = False
    duration_minutes: int = 60
    intensity: str = "extreme"
    setting: str = "in_person"
    tone: str = "cruel"
    orgasm: str = "denied"
    experience: str = "practiced"
    kinks: list[str] = Field(default_factory=list)
    toys: str = ""
    limits: str = ""
    notes: str = ""


@app.get("/api/meta")
async def meta() -> dict:
    return {
        **catalog(),
        "llm_configured": llm_configured(),
        "path": "/",
    }


@app.post("/api/scene")
async def scene(body: PlanRequest) -> dict:
    if not body.adults_confirmed:
        raise HTTPException(status_code=400, detail="Confirm you are 18+.")
    brief = surprise_brief() if body.surprise else body.model_dump()
    try:
        return await plan_scene(brief)
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
