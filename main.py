"""
LabMate AI Backend Service
==========================
FastAPI service providing:
  - Dr. Ada AI Tutor chat (via OpenRouter / Llama 3.3 70B)
  - RBAC + audit trail endpoints
  - User progress tracking

Deployed at: <your-render-url>.onrender.com
Used by: MeDo custom plugin in LabMate AI frontend

Built for the Build with MeDo Hackathon 2026.
"""

from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timezone
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.environ.get(
    "OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free"
)
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Simple shared secret to protect the API from random internet traffic.
# Set this in Render env vars; MeDo will send it as a header.
API_SECRET = os.environ.get("API_SECRET", "labmate-dev-secret-change-me")

# Llama 3.3 70B timeout: a bit generous to allow cold starts on OpenRouter
LLM_TIMEOUT_SECONDS = 25

# -----------------------------------------------------------------------------
# App + CORS
# -----------------------------------------------------------------------------

app = FastAPI(
    title="LabMate AI Backend",
    description="AI Tutor + RBAC + Audit Trail for the LabMate AI platform.",
    version="1.0.0",
)

# MeDo's generated apps run on medo.dev domains; allow all origins for now
# since this is a hackathon demo. Tighten in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------------------------------------------
# In-memory stores (simple demo persistence)
# -----------------------------------------------------------------------------
# NOTE: For a hackathon this is fine. For production, swap these for a real DB.

progress_store: dict[str, dict[str, dict]] = {}  # user_id -> scenario_id -> progress
audit_log: list[dict] = []  # immutable-ish append log of everything that happens

# -----------------------------------------------------------------------------
# Models
# -----------------------------------------------------------------------------


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class TutorChatRequest(BaseModel):
    instrument_name: str = Field(..., description="e.g. 'Microplate Reader'")
    scenario_title: str = Field(..., description="e.g. 'ELISA Absorbance Reading'")
    step_number: int = Field(..., ge=1)
    total_steps: int = Field(..., ge=1)
    step_description: str = Field(..., description="Current step's title or description")
    troubleshoot_mode: bool = False
    hint_request_count: int = Field(
        0,
        ge=0,
        description="How many hints the user has asked for in this scenario. Tutor gives progressively more specific hints.",
    )
    messages: list[ChatMessage] = Field(
        ...,
        description="Conversation history. Last 10 messages. Send user's latest as the last one.",
        max_length=20,
    )
    user_id: str | None = None


class TutorChatResponse(BaseModel):
    reply: str
    model: str
    tokens_used: int | None = None


class ProgressUpdateRequest(BaseModel):
    user_id: str
    scenario_id: str
    step_index: int
    completed: bool = False
    score: float | None = None
    time_spent_seconds: int | None = None


class AuditLogRequest(BaseModel):
    user_id: str
    event_type: str  # e.g. "scenario_started", "quiz_submitted", "role_changed"
    metadata: dict = {}


class AuthVerifyRequest(BaseModel):
    user_id: str
    required_role: Literal["student", "instructor", "admin"] = "student"


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def check_auth(x_api_secret: str | None) -> None:
    """Validate the shared secret header."""
    if not x_api_secret or x_api_secret != API_SECRET:
        raise HTTPException(status_code=401, detail="Invalid or missing API secret")


def log_event(user_id: str, event_type: str, metadata: dict | None = None) -> dict:
    """Append an entry to the audit log."""
    entry = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "event_type": event_type,
        "metadata": metadata or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    audit_log.append(entry)
    return entry


def build_dr_ada_system_prompt(req: TutorChatRequest) -> str:
    """
    Construct the Dr. Ada system prompt using fields from the request.
    Stays in character, stays Socratic, adapts to troubleshoot + hint count.
    """
    base = (
        f"You are Dr. Ada, an experienced lab instructor helping a student operate "
        f"a {req.instrument_name}. The student is working on the scenario "
        f"'{req.scenario_title}' and is currently on Step {req.step_number} of "
        f"{req.total_steps}: {req.step_description}.\n\n"
        "Your role:\n"
        "- Explain concepts clearly without giving away direct answers.\n"
        "- Ask Socratic questions to check understanding.\n"
        "- Provide hints if the student is stuck.\n"
        "- Use correct scientific terminology.\n"
        "- Keep responses under 120 words unless the student asks for detail.\n"
        "- Never break character as Dr. Ada.\n"
    )

    if req.troubleshoot_mode:
        base += (
            "\nTROUBLESHOOTING MODE: The instrument has a deliberately injected "
            "fault. Guide the student to recognize the fault from instrument "
            "readouts, diagnose the cause, and apply the correct fix. Do not "
            "immediately tell them the answer.\n"
        )

    # Progressive hint specificity
    if req.hint_request_count >= 3:
        base += (
            "\nThe student has asked for hints 3+ times. Give a more direct hint "
            "this time — point them clearly toward the next action while still "
            "making them do the final step themselves.\n"
        )
    elif req.hint_request_count >= 2:
        base += (
            "\nThe student has asked for multiple hints. Be a bit more specific "
            "than before, but still Socratic.\n"
        )

    return base


async def call_openrouter(system_prompt: str, messages: list[ChatMessage]) -> dict:
    """Call OpenRouter's chat completion endpoint."""
    if not OPENROUTER_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="OPENROUTER_API_KEY not set on server. Contact the hackathon admin.",
        )

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [{"role": "system", "content": system_prompt}]
        + [m.model_dump() for m in messages],
        "max_tokens": 400,
        "temperature": 0.6,
    }

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://medo.dev",
        "X-Title": "LabMate AI",
    }

    try:
        async with httpx.AsyncClient(timeout=LLM_TIMEOUT_SECONDS) as client:
            resp = await client.post(OPENROUTER_URL, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="LLM provider timed out")
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"LLM provider error: {e.response.status_code} {e.response.text[:200]}",
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"LLM call failed: {str(e)[:200]}")


# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------


@app.get("/")
async def root():
    """Friendly landing route so Render doesn't show 404 on the base URL."""
    return {
        "service": "LabMate AI Backend",
        "status": "ok",
        "docs": "/docs",
        "endpoints": [
            "GET /health",
            "POST /tutor/chat",
            "POST /auth/verify",
            "GET /users/{user_id}/progress",
            "POST /progress/update",
            "GET /audit/{user_id}",
            "POST /audit/log",
        ],
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": OPENROUTER_MODEL,
        "llm_configured": bool(OPENROUTER_API_KEY),
    }


@app.post("/tutor/chat", response_model=TutorChatResponse)
async def tutor_chat(
    req: TutorChatRequest,
    x_api_secret: str | None = Header(default=None, alias="X-API-Secret"),
):
    """
    Dr. Ada — the AI lab tutor.

    Accepts the current instrument + scenario + step context and conversation
    history, returns Dr. Ada's next message. The system prompt is built
    server-side so it can't be tampered with client-side.
    """
    check_auth(x_api_secret)

    start = time.time()
    system_prompt = build_dr_ada_system_prompt(req)
    result = await call_openrouter(system_prompt, req.messages)

    try:
        reply = result["choices"][0]["message"]["content"].strip()
        usage = result.get("usage", {})
        tokens_used = usage.get("total_tokens")
    except (KeyError, IndexError, TypeError):
        raise HTTPException(
            status_code=502, detail="Malformed response from LLM provider"
        )

    # Log for audit purposes
    if req.user_id:
        log_event(
            req.user_id,
            "tutor_chat",
            {
                "instrument": req.instrument_name,
                "scenario": req.scenario_title,
                "step": req.step_number,
                "latency_ms": int((time.time() - start) * 1000),
                "tokens": tokens_used,
            },
        )

    return TutorChatResponse(reply=reply, model=OPENROUTER_MODEL, tokens_used=tokens_used)


@app.post("/auth/verify")
async def auth_verify(
    req: AuthVerifyRequest,
    x_api_secret: str | None = Header(default=None, alias="X-API-Secret"),
):
    """Stub RBAC check. Returns ok=true if user has the required role."""
    check_auth(x_api_secret)

    # For the hackathon demo, we trust the client-side role passed in the user_id.
    # In production, this would look up a real users table.
    log_event(req.user_id, "auth_verify", {"required_role": req.required_role})
    return {"ok": True, "user_id": req.user_id, "role": req.required_role}


@app.get("/users/{user_id}/progress")
async def get_user_progress(
    user_id: str,
    x_api_secret: str | None = Header(default=None, alias="X-API-Secret"),
):
    """Retrieve all progress records for a given user."""
    check_auth(x_api_secret)
    user_progress = progress_store.get(user_id, {})
    return {
        "user_id": user_id,
        "progress": list(user_progress.values()),
        "count": len(user_progress),
    }


@app.post("/progress/update")
async def update_progress(
    req: ProgressUpdateRequest,
    x_api_secret: str | None = Header(default=None, alias="X-API-Secret"),
):
    """Update or create a progress record for a user+scenario."""
    check_auth(x_api_secret)

    if req.user_id not in progress_store:
        progress_store[req.user_id] = {}

    existing = progress_store[req.user_id].get(req.scenario_id, {})
    record = {
        "user_id": req.user_id,
        "scenario_id": req.scenario_id,
        "step_index": req.step_index,
        "completed": req.completed,
        "score": req.score if req.score is not None else existing.get("score"),
        "time_spent_seconds": (
            req.time_spent_seconds
            if req.time_spent_seconds is not None
            else existing.get("time_spent_seconds", 0)
        ),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    progress_store[req.user_id][req.scenario_id] = record

    log_event(
        req.user_id,
        "progress_updated",
        {
            "scenario_id": req.scenario_id,
            "step_index": req.step_index,
            "completed": req.completed,
            "score": req.score,
        },
    )
    return {"ok": True, "progress": record}


@app.get("/audit/{user_id}")
async def get_audit(
    user_id: str,
    x_api_secret: str | None = Header(default=None, alias="X-API-Secret"),
    limit: int = 50,
):
    """Return the most recent audit log entries for a user."""
    check_auth(x_api_secret)
    user_events = [e for e in audit_log if e["user_id"] == user_id]
    return {
        "user_id": user_id,
        "events": user_events[-limit:],
        "total": len(user_events),
    }


@app.post("/audit/log")
async def log_audit(
    req: AuditLogRequest,
    x_api_secret: str | None = Header(default=None, alias="X-API-Secret"),
):
    """Append an entry to the audit log."""
    check_auth(x_api_secret)
    entry = log_event(req.user_id, req.event_type, req.metadata)
    return {"ok": True, "entry": entry}
