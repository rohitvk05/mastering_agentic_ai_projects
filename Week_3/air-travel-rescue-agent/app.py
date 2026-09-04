"""
Air Travel Rescue Agent
=======================

Production-style entry point for the Week 3 project.

This app exposes an OpenAI-compatible Custom LLM endpoint for ElevenLabs:

    POST /v1/chat/completions

Architecture:
    ElevenLabs Voice
        -> FastAPI Custom LLM endpoint
        -> LangGraph Air Travel Rescue workflow
        -> GPT-OSS-120B via Nebius
        -> deterministic airline tools
        -> HITL approval / rebooking / escalation / QA

Run:
    python app.py

or:
    uvicorn app:app --host 0.0.0.0 --port 8013

Then expose locally with:
    ngrok http 8013
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import time
import traceback
import uuid
from pathlib import Path
from typing import Any

import uvicorn
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.types import Command
from num2words import num2words

from src.graph.workflow import build_graph
from src.models.schemas import (
    ApprovalStatus,
    EscalationOutput,
    EscalationReason,
    IntakeOutput,
    PlannerOutput,
    QAOutput,
    ResolutionStatus,
    TriageOutput,
)


# ---------------------------------------------------------------------
# Environment / logging
# ---------------------------------------------------------------------

load_dotenv()

NEBIUS_API_KEY = os.getenv("NEBIUS_API_KEY")
MODEL_BASE_URL = os.getenv("MODEL_BASE_URL")
MODEL_NAME = os.getenv("MODEL_NAME")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID")
ELEVENLABS_MODEL_ID = os.getenv(
    "ELEVENLABS_MODEL_ID",
    "eleven_multilingual_v2",
)

PORT = int(os.getenv("PORT", "8013"))
HOST = os.getenv("HOST", "0.0.0.0")

if not NEBIUS_API_KEY:
    raise RuntimeError("NEBIUS_API_KEY is missing from .env")

if not MODEL_BASE_URL:
    raise RuntimeError("MODEL_BASE_URL is missing from .env")

if not MODEL_NAME:
    raise RuntimeError("MODEL_NAME is missing from .env")


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger("air-travel-rescue")

APP_DIR = Path(__file__).resolve().parent


# ---------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------

llm = ChatOpenAI(
    model=MODEL_NAME,
    api_key=NEBIUS_API_KEY,
    base_url=MODEL_BASE_URL,
    temperature=0,
    max_tokens=2500,
)


# ---------------------------------------------------------------------
# Specialized agent chains
# ---------------------------------------------------------------------

def build_agent_chains() -> dict[str, Any]:
    """Create the structured-output chains used by the LangGraph."""

    intake_prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """
You are the Intake Agent for an Air Travel Rescue system.

Your only job is to extract traveler and disruption information.
Do not recommend flights, solve the disruption, or invent missing data.

Extract:
- origin airport
- destination airport
- flight number
- travel date
- booking ID
- concise issue description
- arrival deadline
- maximum acceptable extra cost
- traveler preferences
- missing information

Rules:
1. Normalize unambiguous airport locations to IATA codes.
2. Return null when a value is not supplied and cannot safely be inferred.
3. Put required missing fields in missing_information.
4. Use ISO-8601 dates/times when enough information is available.
5. Never fabricate flight numbers, booking IDs, dates, or constraints.
""",
            ),
            ("human", "{traveler_message}"),
        ]
    )

    triage_prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """
You are the Triage Agent for an Air Travel Rescue system.

Classify the disruption and determine whether recovery is required.

Supported disruption types:
- cancelled
- delayed
- missed_connection
- schedule_change
- unsupported

Severity:
- low
- medium
- high
- critical

Rules:
1. Cancelled flights normally require recovery.
2. A delay requires recovery when it threatens a deadline or connection.
3. Use missed_connection when an inbound disruption makes the onward
   connection infeasible.
4. Use unsupported for issues outside flight recovery such as card/refund
   disputes, baggage claims, immigration questions, or unrelated requests.
5. Do not search flights.
6. Do not recommend a recovery option.
7. Do not invent facts.
""",
            ),
            (
                "human",
                """
Origin: {origin}
Destination: {destination}
Flight number: {flight_number}
Travel date: {travel_date}
Issue: {issue_description}
Arrival deadline: {arrival_deadline}
Maximum extra cost: {max_extra_cost}
Preferences: {preferences}
""",
            ),
        ]
    )

    planner_prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """
You are the Recovery Planner Agent for an Air Travel Rescue system.

Choose the best option ONLY from the viable ranked flights supplied to you.

Do not invent flights.
Do not select a flight outside the provided options.
Do not recalculate deterministic feasibility.
Do not perform booking actions.

Consider:
- arrival deadline
- traveler preferences
- number of stops
- additional cost
- departure/arrival time
- convenience

Rules:
1. Respect hard traveler constraints.
2. Prefer nonstop when other factors are reasonably similar.
3. Prefer lower cost when it does not materially worsen the itinerary.
4. Prefer earlier arrival when urgency matters.
5. Any rebooking requires explicit traveler approval.
6. Return concise decision factors, not hidden chain-of-thought.
""",
            ),
            (
                "human",
                """
Origin: {origin}
Destination: {destination}
Arrival deadline: {arrival_deadline}
Maximum extra cost: {max_extra_cost}
Preferences: {preferences}

Viable ranked flight options:
{ranked_options}
""",
            ),
        ]
    )

    escalation_prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """
You are the Escalation Agent for an Air Travel Rescue system.

Prepare a concise structured handoff to a human travel-support agent when
automated recovery cannot safely complete the task.

Valid reasons:
- no_viable_flight
- tool_failure
- unsupported_request
- policy_restriction
- user_requested_human
- other

Rules:
1. Repeated flight-inventory errors should be tool_failure.
2. If flight search succeeds but no option satisfies the constraints,
   use no_viable_flight.
3. Do not invent attempted actions.
4. Summarize what automation already tried so the human does not repeat work.
5. Provide one concrete recommended human action.
6. Do not modify bookings.
""",
            ),
            (
                "human",
                """
Issue: {issue_description}
Disruption: {disruption_type}
Severity: {severity}
Route: {origin} -> {destination}
Original flight: {original_flight}
Last error: {last_error}
Retry count: {retry_count}
Viable ranked options: {ranked_options}
Actions attempted: {action_history}
""",
            ),
        ]
    )

    qa_prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """
You are the QA Agent for an Air Travel Rescue system.

Review the completed interaction and evaluate:
- correct disruption classification
- whether traveler constraints were respected
- whether appropriate tools were used
- whether approval was obtained before write actions
- whether unsupported actions were attempted
- unnecessary tool calls
- whether resolution/escalation was appropriate
- whether follow-up is required

Do not change the booking.
Do not recommend new flights.
Do not invent events absent from the workflow state.
""",
            ),
            (
                "human",
                """
Issue description: {issue_description}
Disruption type: {disruption_type}
Arrival deadline: {arrival_deadline}
Maximum extra cost: {max_extra_cost}
Preferences: {preferences}
Original flight: {original_flight}
Recommended plan: {recommended_plan}
Approval status: {approval_status}
Booking updated: {booking_updated}
Resolution status: {resolution_status}
Resolution summary: {resolution_summary}
Action history: {action_history}
Escalation: {escalation_output}
""",
            ),
        ]
    )

    return {
        "intake_chain": intake_prompt | llm.with_structured_output(IntakeOutput),
        "triage_chain": triage_prompt | llm.with_structured_output(TriageOutput),
        "planner_chain": planner_prompt | llm.with_structured_output(PlannerOutput),
        "escalation_chain": escalation_prompt
        | llm.with_structured_output(EscalationOutput),
        "qa_chain": qa_prompt | llm.with_structured_output(QAOutput),
    }


chains = build_agent_chains()

graph = build_graph(
    intake_chain=chains["intake_chain"],
    triage_chain=chains["triage_chain"],
    planner_chain=chains["planner_chain"],
    escalation_chain=chains["escalation_chain"],
    qa_chain=chains["qa_chain"],
)

elevenlabs_client = (
    ElevenLabs(api_key=ELEVENLABS_API_KEY)
    if ELEVENLABS_API_KEY
    else None
)


# ---------------------------------------------------------------------
# Voice formatting
# ---------------------------------------------------------------------

_DIGIT_WORDS = {
    "0": "oh",
    "1": "one",
    "2": "two",
    "3": "three",
    "4": "four",
    "5": "five",
    "6": "six",
    "7": "seven",
    "8": "eight",
    "9": "nine",
}


def flight_number_to_speech(flight_number: str | None) -> str:
    """AS102 -> 'A S one oh two'."""

    if not flight_number:
        return ""

    match = re.fullmatch(r"([A-Za-z]+)(\d+)", str(flight_number).strip())

    if not match:
        return str(flight_number)

    letters, digits = match.groups()

    spoken_letters = " ".join(letters.upper())
    spoken_digits = " ".join(_DIGIT_WORDS[digit] for digit in digits)

    return f"{spoken_letters} {spoken_digits}"


def money_to_speech(amount: float | int | str | None) -> str:
    """50.00 -> 'fifty dollars'."""

    if amount is None:
        return "zero dollars"

    amount = float(amount)
    dollars = int(amount)
    cents = round((amount - dollars) * 100)

    result = (
        f"{num2words(dollars)} "
        f"{'dollar' if dollars == 1 else 'dollars'}"
    )

    if cents:
        result += (
            f" and {num2words(cents)} "
            f"{'cent' if cents == 1 else 'cents'}"
        )

    return result


def speech_sanitize_text(text: str) -> str:
    """
    Convert common machine-friendly travel strings into better TTS text.

    Examples:
      $50.00 -> fifty dollars
      AS102  -> A S one oh two
    """

    if not text:
        return ""

    def replace_money(match: re.Match[str]) -> str:
        return money_to_speech(match.group(1))

    text = re.sub(
        r"\$(\d+(?:\.\d{1,2})?)",
        replace_money,
        text,
    )

    def replace_flight(match: re.Match[str]) -> str:
        return flight_number_to_speech(match.group(1))

    text = re.sub(
        r"\b([A-Z]{2}\d{2,4})\b",
        replace_flight,
        text,
    )

    return text


def format_voice_response(result: dict[str, Any]) -> str:
    """Turn LangGraph state into natural, speech-friendly text."""

    interrupts = result.get("__interrupt__") or []

    if interrupts:
        interrupt_obj = interrupts[0]
        value = getattr(interrupt_obj, "value", {})

        if isinstance(value, dict):
            flight_number = value.get("flight_number")
            additional_cost = value.get("additional_cost", 0)

            spoken_flight = flight_number_to_speech(flight_number)
            spoken_cost = money_to_speech(additional_cost)

            return (
                f"I found flight {spoken_flight} for an additional "
                f"{spoken_cost}. Would you like me to rebook you?"
            )

        return (
            "I found a recovery option. "
            "Would you like me to proceed?"
        )

    if result.get("resolution_status") == ResolutionStatus.RESOLVED:
        action = result.get("pending_action")

        if action and getattr(action, "flight_number", None):
            spoken_flight = flight_number_to_speech(action.flight_number)
            return (
                "Done. I've successfully rebooked you onto "
                f"flight {spoken_flight}."
            )

        return "Done. Your flight has been successfully rebooked."

    escalation = result.get("escalation_output")

    if escalation:
        if escalation.reason == EscalationReason.NO_VIABLE_FLIGHT:
            return (
                "I'm sorry, I don't have any remaining flights that meet "
                "your requirements. A travel support agent will need to help "
                "with other routes or dates."
            )

        if escalation.reason == EscalationReason.TOOL_FAILURE:
            return (
                "I'm sorry, the flight system is temporarily unavailable. "
                "A travel support agent will need to continue from here."
            )

        if escalation.reason == EscalationReason.UNSUPPORTED_REQUEST:
            return (
                "I can't complete that request through automated flight "
                "recovery. A support agent can help you further."
            )

        return (
            "I wasn't able to complete the recovery automatically. "
            "A travel support agent will need to continue from here."
        )

    if result.get("resolution_summary"):
        return speech_sanitize_text(result["resolution_summary"])

    return "I need a little more information to continue."


# ---------------------------------------------------------------------
# LangGraph conversation / HITL handling
# ---------------------------------------------------------------------

def graph_is_waiting_for_input(config: dict[str, Any]) -> bool:
    snapshot = graph.get_state(config)

    # Most reliable check: an actual LangGraph interrupt is attached to a task.
    for task in snapshot.tasks:
        if getattr(task, "interrupts", ()):
            return True

    pending_action = snapshot.values.get("pending_action")
    approval_status = snapshot.values.get("approval_status")
    next_nodes = snapshot.next or ()

    # Fallback for LangGraph versions that expose the paused node this way.
    if (
        pending_action is not None
        and approval_status == ApprovalStatus.PENDING
        and "await_approval" in next_nodes
    ):
        return True

    return False


def run_voice_turn(thread_id: str, user_text: str) -> dict[str, Any]:
    """
    Start a new recovery workflow or resume a paused HITL approval.
    """

    config = {
        "configurable": {
            "thread_id": thread_id,
        }
    }

    snapshot = graph.get_state(config)

    logger.info("=== VOICE TURN ===")
    logger.info("Thread: %s", thread_id)
    logger.info("User: %s", user_text)
    logger.info("Next: %s", snapshot.next)
    logger.info(
        "Approval: %s",
        snapshot.values.get("approval_status"),
    )
    logger.info(
        "Pending action: %s",
        snapshot.values.get("pending_action"),
    )

    if graph_is_waiting_for_input(config):
        logger.info("MODE: RESUME")

        return graph.invoke(
            Command(resume=user_text),
            config=config,
        )

    logger.info("MODE: NEW REQUEST")

    state = {
        "messages": [
            HumanMessage(content=user_text)
        ],
        "approval_status": ApprovalStatus.PENDING,
        "retry_count": 0,
        "simulate_search_failure": False,
        "simulate_persistent_search_failure": False,
    }

    return graph.invoke(
        state,
        config=config,
    )


# ---------------------------------------------------------------------
# ElevenLabs duplicate-request protection
# ---------------------------------------------------------------------
#
# ElevenLabs may retry the same Custom LLM request while a slower agentic
# workflow is still executing. Without deduplication, those retries can start
# multiple LangGraph executions against the same checkpoint.
#

_inflight_turns: dict[str, asyncio.Task] = {}
_inflight_lock = asyncio.Lock()


def make_turn_key(thread_id: str, user_text: str) -> str:
    normalized = " ".join(user_text.strip().lower().split())

    digest = hashlib.sha256(
        normalized.encode("utf-8")
    ).hexdigest()[:16]

    return f"{thread_id}:{digest}"


async def execute_voice_turn_once(
    thread_id: str,
    user_text: str,
) -> tuple[dict[str, Any], bool]:
    """
    Ensure duplicate ElevenLabs retries share one LangGraph execution.

    Returns:
        (result, is_owner)
    """

    turn_key = make_turn_key(thread_id, user_text)

    async with _inflight_lock:
        existing_task = _inflight_turns.get(turn_key)

        if existing_task:
            logger.info(
                "DUPLICATE ELEVENLABS REQUEST — REUSING IN-FLIGHT TURN: %s",
                turn_key,
            )

            task = existing_task
            is_owner = False

        else:
            logger.info(
                "STARTING NEW LANGGRAPH TURN: %s",
                turn_key,
            )

            task = asyncio.create_task(
                asyncio.to_thread(
                    run_voice_turn,
                    thread_id,
                    user_text,
                )
            )

            _inflight_turns[turn_key] = task
            is_owner = True

    try:
        # Do not allow an ElevenLabs retry/disconnect to cancel the shared
        # LangGraph task.
        result = await asyncio.shield(task)

        return result, is_owner

    finally:
        if task.done():
            async with _inflight_lock:
                if _inflight_turns.get(turn_key) is task:
                    _inflight_turns.pop(turn_key, None)


# ---------------------------------------------------------------------
# ElevenLabs request helpers
# ---------------------------------------------------------------------

def extract_elevenlabs_conversation_id(
    messages: list[dict[str, Any]],
) -> str | None:
    """
    Reads the stable ElevenLabs conversation ID inserted in the agent prompt:

        ELEVENLABS_CONVERSATION_ID={{system__conversation_id}}
    """

    for message in messages:
        if message.get("role") != "system":
            continue

        content = message.get("content") or ""

        match = re.search(
            r"ELEVENLABS_CONVERSATION_ID=([A-Za-z0-9_-]+)",
            content,
        )

        if match:
            return match.group(1)

    return None


def create_sse_chunk(
    text: str,
    model: str,
    finish_reason: str | None = None,
) -> dict[str, Any]:
    """Create an OpenAI-compatible streamed Chat Completions chunk."""

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": (
                    {"content": text}
                    if text
                    else {}
                ),
                "finish_reason": finish_reason,
            }
        ],
    }


# ---------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------

app = FastAPI(
    title="Air Travel Rescue Agent",
    version="1.0.0",
    description=(
        "OpenAI-compatible Custom LLM backend for the ElevenLabs "
        "Air Travel Rescue voice agent."
    ),
)


@app.get("/", response_class=FileResponse)
def root() -> FileResponse:
    """Serve the browser-based voice interface."""

    return FileResponse(APP_DIR / "static" / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "air-travel-rescue-agent",
    }


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    """Avoid a noisy 404 when browsers request a tab icon."""

    return Response(status_code=204)


@app.post("/api/speech")
async def synthesize_speech(request: Request) -> Response:
    """Generate speech with the configured ElevenLabs voice."""

    if not elevenlabs_client or not ELEVENLABS_VOICE_ID:
        raise HTTPException(
            status_code=503,
            detail=(
                "ElevenLabs voice is not configured. Set "
                "ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID in .env."
            ),
        )

    body = await request.json()
    text = body.get("text")

    if not isinstance(text, str) or not text.strip():
        raise HTTPException(status_code=400, detail="Speech text is required.")

    if len(text) > 5000:
        raise HTTPException(status_code=400, detail="Speech text is too long.")

    def generate_audio() -> bytes:
        chunks = elevenlabs_client.text_to_speech.convert(
            voice_id=ELEVENLABS_VOICE_ID,
            text=text.strip(),
            model_id=ELEVENLABS_MODEL_ID,
            output_format="mp3_44100_128",
        )
        return b"".join(chunks)

    try:
        audio = await asyncio.to_thread(generate_audio)
    except Exception:
        logger.exception("ElevenLabs speech generation failed")
        raise HTTPException(
            status_code=502,
            detail=(
                "ElevenLabs could not generate audio. Verify the configured "
                "API key, voice ID, and model ID."
            ),
        )

    return Response(
        content=audio,
        media_type="audio/mpeg",
        headers={"Cache-Control": "no-store"},
    )


@app.post("/v1/chat/completions")
async def chat_completion(
    request: Request,
) -> StreamingResponse:
    """
    ElevenLabs Custom LLM endpoint.

    Accepts an OpenAI-compatible Chat Completions request and returns
    Server-Sent Events (SSE).
    """

    body = await request.json()

    messages = body.get("messages", [])
    model = body.get(
        "model",
        "air-travel-rescue",
    )

    user_text = None

    for message in reversed(messages):
        if message.get("role") == "user":
            user_text = message.get("content")
            break

    if not user_text:
        raise HTTPException(
            status_code=400,
            detail="No user message received.",
        )

    extra_body = body.get(
        "elevenlabs_extra_body",
        {},
    ) or {}

    thread_id = (
        extra_body.get("UUID")
        or extra_body.get("thread_id")
        or body.get("user_id")
        or extract_elevenlabs_conversation_id(messages)
    )

    if not thread_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "Unable to determine a stable ElevenLabs conversation ID. "
                "Add ELEVENLABS_CONVERSATION_ID={{system__conversation_id}} "
                "to the ElevenLabs agent prompt."
            ),
        )

    logger.info("=== ELEVENLABS REQUEST ===")
    logger.info("LANGGRAPH THREAD ID: %s", thread_id)
    logger.info("USER TEXT: %s", user_text)

    async def event_stream():
        try:
            # IMPORTANT:
            # Do not manually stream a filler such as "Let me check that".
            # ElevenLabs Soft Timeout should provide that conversational filler.
            #
            # ElevenLabs may retry this request while LangGraph is still running;
            # execute_voice_turn_once() makes those retries idempotent.
            result, _ = await execute_voice_turn_once(
                thread_id,
                user_text,
            )

            reply = format_voice_response(result)

            logger.info(
                "VOICE RESPONSE: %s",
                reply,
            )

            response_chunk = create_sse_chunk(
                reply,
                model,
            )

            yield (
                "data: "
                + json.dumps(response_chunk)
                + "\n\n"
            )

            final_chunk = create_sse_chunk(
                "",
                model,
                finish_reason="stop",
            )

            yield (
                "data: "
                + json.dumps(final_chunk)
                + "\n\n"
            )

            yield "data: [DONE]\n\n"

        except Exception:
            logger.error(
                "CUSTOM LLM ERROR:\n%s",
                traceback.format_exc(),
            )

            # Return a valid SSE response instead of crashing the voice
            # conversation with an invalid Custom LLM response.
            safe_reply = (
                "I'm sorry, I couldn't complete that request right now. "
                "Please try again."
            )

            yield (
                "data: "
                + json.dumps(
                    create_sse_chunk(
                        safe_reply,
                        model,
                    )
                )
                + "\n\n"
            )

            yield (
                "data: "
                + json.dumps(
                    create_sse_chunk(
                        "",
                        model,
                        finish_reason="stop",
                    )
                )
                + "\n\n"
            )

            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------
# Local server
# ---------------------------------------------------------------------

if __name__ == "__main__":
    logger.info(
        "Starting Air Travel Rescue Agent on http://%s:%s",
        HOST,
        PORT,
    )

    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
        log_level="info",
    )
