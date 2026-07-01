"""Rehearse voice interview — a LiveKit Agents worker.

Adapted from my jobnova mock-interview agent. What's different here:
  - The interview is grounded in the JOB'S competencies (pulled from the Rehearse API),
    not a fixed script.
  - It runs as one conversational interviewer: it works through the competencies, asks a
    natural follow-up when the candidate actually answers, replies when they ask you
    something, and wraps up when they're done or ask to stop.
  - When it ends it posts the transcript back to the Rehearse API, which runs the
    calibrated judge and stores the scores — so a spoken interview flows into the exact
    same evaluation as a typed one.

A silence-timeout fallback wraps things up if the candidate goes quiet.
"""

import asyncio
import logging
import os
from dataclasses import dataclass, field

import httpx
from dotenv import load_dotenv
from livekit import agents
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    ChatContext,
    EndpointingOptions,
    InterruptionOptions,
    JobContext,
    RunContext,
    StopResponse,
    TurnHandlingOptions,
    function_tool,
)
from livekit.agents.llm import ChatMessage
from livekit.plugins import deepgram, groq, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

load_dotenv(".env.local")

REHEARSE_API_URL = os.getenv("REHEARSE_API_URL", "http://localhost:8000")
# Which job to interview for. The web client will pass this via room metadata later;
# for now (and for testing in the LiveKit console) it comes from the environment.
REHEARSE_JOB_ID = os.getenv("REHEARSE_JOB_ID")

INTERVIEW_SILENCE_TIMEOUT = 150  # if the candidate goes quiet this long, wrap up
FALLBACK_IDLE_GRACE = 15         # once due, wait for a natural pause before ending

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rehearse-agent")


@dataclass
class Interview:
    """What the interview is grounded in."""

    job_id: int | None
    competencies: list[tuple[str, str]] = field(default_factory=list)  # (name, description)


async def wait_for_pause(session: AgentSession) -> None:
    try:
        await asyncio.wait_for(session.wait_for_idle(), timeout=FALLBACK_IDLE_GRACE)
    except Exception:
        pass


def build_transcript(session: AgentSession) -> list[dict[str, str]]:
    """Turn the session history into the {speaker, text} turns the API expects."""
    turns: list[dict[str, str]] = []
    for item in session.history.items:
        if getattr(item, "type", None) != "message" or not item.text_content:
            continue
        if item.role == "assistant":
            turns.append({"speaker": "interviewer", "text": item.text_content.strip()})
        elif item.role == "user":
            turns.append({"speaker": "candidate", "text": item.text_content.strip()})
    return turns


async def score_and_store(interview: Interview, session: AgentSession) -> None:
    """Post the transcript to the Rehearse API so the judge scores it and it's saved."""
    if interview.job_id is None:
        logger.info(">> No job id — skipping scoring (was this a playground test?)")
        return
    turns = build_transcript(session)
    if not turns:
        return
    try:
        async with httpx.AsyncClient(base_url=REHEARSE_API_URL, timeout=120) as client:
            created = await client.post(f"/jobs/{interview.job_id}/sessions", json={"turns": turns})
            created.raise_for_status()
            session_id = created.json()["id"]
            scored = await client.post(f"/sessions/{session_id}/evaluate")
            scored.raise_for_status()
        logger.info(">> Scored and stored as session %s", session_id)
    except Exception as e:
        logger.warning("Could not score/store the interview: %s", e)


async def close_interview(interview: Interview, session: AgentSession) -> None:
    await session.generate_reply(
        instructions=(
            "Warmly thank the candidate for their time, let them know this is the end of "
            "the interview and that they'll see their scores shortly. Keep it short."
        )
    )
    await score_and_store(interview, session)
    logger.info(">> INTERVIEW COMPLETE")


def check_required_env() -> None:
    required = ["LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "GROQ_API_KEY", "DEEPGRAM_API_KEY"]
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise SystemExit(
            "\nMissing required environment variable(s): "
            + ", ".join(missing)
            + "\nAdd them to apps/agent/.env.local (see .env.example).\n"
        )


def _job_id_from_room(room_name: str) -> str | None:
    # Rooms created by the web app are named "rehearse-<job_id>-<hash>".
    parts = room_name.split("-")
    if len(parts) >= 2 and parts[0] == "rehearse" and parts[1].isdigit():
        return parts[1]
    return None


async def fetch_interview(ctx: JobContext) -> Interview:
    """Load the job's competencies so questions are grounded. The job id comes from the
    room name (set by the web app); falls back to REHEARSE_JOB_ID for console testing."""
    job_id = _job_id_from_room(ctx.room.name) or REHEARSE_JOB_ID
    if not job_id:
        logger.warning(">> No job id (room or env) — running a generic interview")
        return Interview(job_id=None)
    try:
        async with httpx.AsyncClient(base_url=REHEARSE_API_URL, timeout=30) as client:
            resp = await client.get(f"/jobs/{job_id}")
            resp.raise_for_status()
            job = resp.json()
        comps = [(c["name"], c["description"]) for c in job["competencies"]]
        logger.info(">> Interviewing for job %s with %s competencies", job["id"], len(comps))
        return Interview(job_id=int(job["id"]), competencies=comps)
    except Exception as e:
        logger.warning("Could not load job %s: %s — generic interview", job_id, e)
        return Interview(job_id=None)


# If the candidate says any of these, wrap up instead of pushing on.
_END_PHRASES = (
    "end the interview",
    "end this interview",
    "stop the interview",
    "no more questions",
    "i'm done",
    "im done",
    "that's all",
    "thats all",
    "let's end",
    "lets end",
    "we can stop",
    "when will this end",
    "how long is",
)


def wants_to_end(message: ChatMessage) -> bool:
    text = (message.text_content or "").lower()
    return any(phrase in text for phrase in _END_PHRASES)


class InterviewAgent(Agent):
    """One conversational interviewer.

    It works through the job's competencies, follows up when the candidate gives a real
    answer, answers questions the candidate asks, and calls end_interview when they're
    done. Letting the model drive the turns (rather than forcing a script) is what makes
    it feel like a conversation instead of an interrogation — the earlier code-driven
    version couldn't follow up or respond to the candidate.
    """

    def __init__(self, interview: Interview) -> None:
        if interview.competencies:
            areas = "\n".join(f"- {name}: {desc}" for name, desc in interview.competencies)
        else:
            areas = "- The candidate's most relevant recent experience for the role."
        super().__init__(
            instructions=f"""
You are a warm, professional AI interviewer for Rehearse running a spoken mock interview.
Run it like a real, friendly conversation:

- Start by greeting the candidate and asking them to briefly introduce themselves.
- Then work through these areas, ONE AT A TIME, in order:
{areas}
- For each area, ask one focused question. If the candidate gives a real, substantive
  answer, ask ONE natural follow-up that builds only on what they ACTUALLY said. If they
  say they don't know or don't really answer, kindly acknowledge it and move on — never
  claim they said something they didn't.
- If the candidate asks YOU a question, answer it briefly and warmly, then carry on.
- Ask only ONE question per turn. Keep it conversational, not an interrogation.
- When you've covered the areas and the candidate has nothing more to add, or if they ask
  to stop, call the end_interview tool. It speaks the closing line for you, so do not say
  goodbye yourself.
""",
        )
        self._interview = interview
        self._closed = False
        self._fallback_task: asyncio.Task | None = None

    async def on_enter(self) -> None:
        logger.info(">> INTERVIEW — STARTED (%s competencies)", len(self._interview.competencies))
        await self.session.generate_reply(
            instructions=(
                "Warmly welcome the candidate to their Rehearse mock interview, briefly say "
                "you'll walk through a few areas relevant to the role, then ask them to "
                "introduce themselves."
            )
        )
        self._arm_fallback()

    def _arm_fallback(self) -> None:
        # Reset the silence timer each turn so it only fires when the candidate truly stops.
        if self._fallback_task and not self._fallback_task.done():
            self._fallback_task.cancel()
        self._fallback_task = asyncio.create_task(self._fallback())

    async def _fallback(self) -> None:
        try:
            await asyncio.sleep(INTERVIEW_SILENCE_TIMEOUT)
            await wait_for_pause(self.session)
        except asyncio.CancelledError:
            return
        if not self._closed:
            logger.warning(">> FALLBACK: long silence — wrapping up")
            await self._close()

    async def on_exit(self) -> None:
        if self._fallback_task and not self._fallback_task.done():
            self._fallback_task.cancel()

    async def on_user_turn_completed(self, turn_ctx: ChatContext, new_message: ChatMessage) -> None:
        # No StopResponse on a normal turn: let the model reply naturally, so it can ask
        # follow-ups and answer the candidate's questions. Just reset the silence timer and
        # honor an explicit request to stop.
        if self._closed:
            raise StopResponse()
        if wants_to_end(new_message):
            logger.info(">> Candidate asked to end")
            await self._close()
            raise StopResponse()
        self._arm_fallback()

    @function_tool
    async def end_interview(self, context: RunContext):
        """Close the interview once the areas are covered and the candidate is done."""
        await self._close()
        return None

    async def _close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._fallback_task and not self._fallback_task.done():
            self._fallback_task.cancel()
        await close_interview(self._interview, self.session)


server = AgentServer()


@server.rtc_session()
async def entrypoint(ctx: JobContext):
    logger.info(">> New interview session — connecting...")
    await ctx.connect()
    interview = await fetch_interview(ctx)

    # Deepgram for speech (STT + TTS), Groq for the interviewer LLM, local VAD. Scoring
    # happens later on the backend with Claude — the interviewer voice can stay cheap.
    session = AgentSession(
        stt=deepgram.STT(model="nova-3"),
        llm=groq.LLM(model="llama-3.3-70b-versatile"),
        tts=deepgram.TTS(model="aura-2-andromeda-en"),
        vad=silero.VAD.load(activation_threshold=0.75, min_silence_duration=0.6),
        turn_handling=TurnHandlingOptions(
            turn_detection=MultilingualModel(),
            endpointing=EndpointingOptions(min_delay=1.0, max_delay=6.0),
            # Interruptions ON so the candidate can cut in — e.g. to say they're done —
            # instead of their words being dropped while the agent is talking. Use
            # headphones so the agent's own voice doesn't trigger the mic.
            interruption=InterruptionOptions(enabled=True),
        ),
    )

    await session.start(agent=InterviewAgent(interview), room=ctx.room)


if __name__ == "__main__":
    check_required_env()
    agents.cli.run_app(server)
