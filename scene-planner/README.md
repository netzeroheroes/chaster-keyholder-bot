# Scene Planner

Standalone femdom scene planner. Uses **OpenRouter** (`LLM_API_KEY` in the repo `.env`). It does not use Cursor models and does not need `agent-sdk login`.

Flow:

1. Kit quiz: toys, kinks, hard limits.
2. Ask for a session of any length (30 minutes is only an example).
3. Two questions: what the session should do to him, and orgasm policy.
4. The bot writes a timed itinerary from that kit. Follow-ups rewrite the whole scene.

It is not the Chaster extension. Run it as its own local server.

Adults 18+ only. Default dynamic is female dominant / male submissive.

```powershell
cd C:\Users\andre\chatbot
.\.venv\Scripts\python.exe scene-planner\server.py
```

Open http://127.0.0.1:8787

Training is `scene-planner/instructions.md` plus `scene-planner/tests`. Change the prompt, keep the tests green, then send a scene you like or hate and tighten the instructions.
