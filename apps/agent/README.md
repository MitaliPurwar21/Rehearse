# Voice interview agent

A LiveKit Agents worker that conducts the mock interview by voice. Ported and adapted
from my jobnova take-home: here the questions are grounded in a job's competencies
(pulled from the Rehearse API), and the transcript is posted back so the calibrated
judge scores it — same evaluation as a typed interview.

## Accounts you need (free tiers)

- **LiveKit** (livekit.io) — real-time audio. Create a project; copy the URL + API key/secret.
- **Deepgram** (deepgram.com) — speech-to-text + text-to-speech.
- **Groq** (console.groq.com) — the interviewer's LLM (free).

## Setup

```bash
cd apps/agent
python3.13 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env.local          # fill in the keys above
```

Also set:
- `REHEARSE_API_URL` — your running backend (local `http://localhost:8000`, or your Render URL).
- `REHEARSE_JOB_ID` — create a job first (`POST /jobs`) and put its id here, so the
  interview is grounded in that role's competencies.

## Run + test

```bash
python agent.py dev
```

Then talk to it in the **LiveKit Agents Playground** (https://agents-playground.livekit.io) —
connect it to your LiveKit project and it gives you a mic in the browser, no custom
frontend needed yet. Speak through the interview; when it closes, it posts the transcript
to the backend and you'll see the scored session there (`GET /sessions/{id}`).

## How it flows

1. On connect, it reads the job's competencies from `REHEARSE_API_URL`.
2. Intro → one question per competency (+ a follow-up) → your questions → close.
3. On close, it POSTs the transcript to `/jobs/{id}/sessions` then `/sessions/{id}/evaluate`,
   so the spoken interview lands in the same judge + database as a typed one.

Stages advance in code with a per-stage silence-timeout fallback, so the interview keeps
moving even if you go quiet.
