# Deploying Rehearse from scratch

A complete walkthrough with no prior experience assumed. By the end you'll have the app
live on the internet, with both **typed** and **voice** interviews working.

The pieces:

| Piece | Where it runs | Host |
|---|---|---|
| Backend API (FastAPI) | the cloud | Render |
| Frontend (Next.js) | the cloud | Vercel |
| Database (Postgres) | the cloud | Neon |
| Voice agent | your laptop (for now) | you run it |

The order matters — do the sections top to bottom.

---

## 0. Accounts and tools you'll need (all have free tiers)

Sign up for these first:

- **GitHub** — the code lives here; Render and Vercel deploy from it.
- **Anthropic** (console.anthropic.com) — the AI judge. Add ~$5 of credit under Billing.
- **Neon** (neon.tech) — the database.
- **Render** (render.com) — hosts the backend.
- **Vercel** (vercel.com) — hosts the frontend.

For the voice interview, also:
- **LiveKit** (livekit.io) — real-time audio.
- **Deepgram** (deepgram.com) — speech to text and back.
- **Groq** (console.groq.com) — the interviewer's LLM (free).

On your Mac you'll need **Python 3.13**, **Node.js**, and **git**. (`python3.13 --version`,
`node --version`, `git --version` to check.)

---

## 1. Get the code onto GitHub

If it's already your repo (`MitaliPurwar21/Rehearse`), just make sure your latest work is
pushed:

```bash
cd ~/Desktop/rehearse
git add -A
git commit -m "Deploy"
git push origin main
```

Render and Vercel read from GitHub, so **anything not pushed won't deploy.**

---

## 2. Database — Neon

1. At **neon.tech**, create a project (any name).
2. Copy the **connection string**. It must start with `postgresql://` and usually ends
   with `?sslmode=require` — use Neon's copy button to get the whole thing.
3. Keep it handy; you'll paste it into Render in the next step.

You don't create any tables yourself — the app makes them on first startup.

---

## 3. Backend — Render

1. In **Render**: **New → Blueprint**, and select this repo. It reads `render.yaml` and
   sets up a service called `rehearse-api`. Leave **Blueprint Path** blank.
2. It will ask you to fill in these secrets (they're marked "set in dashboard"):
   - `ANTHROPIC_API_KEY` — your Claude key (`sk-ant-...`).
   - `DATABASE_URL` — the Neon string from step 2.
   - `CORS_ORIGINS` — set to `http://localhost:3000` for now; you'll fix it in step 5.
   - *(Leave the LiveKit ones for step 6.)*
3. Apply and wait for it to build (a few minutes).
4. When it's live, open `https://<your-service>.onrender.com/health` — you want
   `{"status":"ok"}`. Copy that base URL; you'll need it next.

> The free tier sleeps after ~15 minutes idle, so the first request after a nap takes
> ~30 seconds to wake up. Normal — just be patient in a demo.

---

## 4. Frontend — Vercel

1. In **Vercel**: **Add New → Project**, import this repo.
2. Set **Root Directory** to `apps/web` (so it builds only the frontend).
3. Add an environment variable:
   - `NEXT_PUBLIC_API_URL` = your Render backend URL from step 3 (no trailing slash).
4. Deploy, then copy your site URL (e.g. `https://rehearse-eight.vercel.app`).

---

## 5. Connect the two (CORS)

By default a browser won't let your website call your backend (different domains). So tell
the backend to allow the site:

1. Render → `rehearse-api` → **Environment** → set `CORS_ORIGINS` to your Vercel URL
   (comma-separate to also keep localhost):
   ```
   https://rehearse-eight.vercel.app,http://localhost:3000
   ```
   **No trailing slash**, and use the exact URL from your address bar.
2. Save → wait for Render to redeploy.

Now open your Vercel site, paste a job description, and try the **typed** interview — you
should get scores. That confirms the backend, database, and frontend are all wired up.

---

## 6. Voice interview

The voice interview needs three more accounts and a small program (the "agent") that you
run on your laptop.

### 6a. Get the keys
- **LiveKit** (cloud.livekit.io): create a project → **Settings → Keys**. Copy the
  **URL** (`wss://...`), **API Key**, and **API Secret**.
- **Deepgram** (console.deepgram.com): **API Keys → Create** → copy the key.
- **Groq** (console.groq.com): **API Keys → Create** → copy the key.

### 6b. Tell the backend about LiveKit
Render → `rehearse-api` → Environment → add the three LiveKit values (same project you'll
run the agent against):
```
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=API...
LIVEKIT_API_SECRET=...
```
Save → wait for Live. (Without these, the site shows "voice interview is not configured".)

### 6c. Run the agent
```bash
cd ~/Desktop/rehearse/apps/agent
python3.13 -m venv venv && source venv/bin/activate
pip install -r requirements.txt          # first time only; it's a big install
cp .env.example .env.local
```
Open `.env.local` (`open -e .env.local`) and fill in:
```
LIVEKIT_URL=...        # same LiveKit project as the backend
LIVEKIT_API_KEY=...
LIVEKIT_API_SECRET=...
GROQ_API_KEY=...
DEEPGRAM_API_KEY=...
REHEARSE_API_URL=https://<your-service>.onrender.com   # your live backend
REHEARSE_JOB_ID=       # leave blank — the website provides the job
```
Then run it and leave it running:
```bash
python agent.py dev
```
Wait for the line ending in `registered worker`.

> The agent must be running for voice interviews to work. Hosting it (so you don't run it
> locally) is a later improvement; for now it lives on your laptop during a demo.

---

## 7. Use it

Open your Vercel site with **headphones on**:
1. Paste a job description → **Extract competencies**.
2. **🎙️ Voice interview → Start voice interview** → allow the microphone.
3. Talk to the interviewer. When finished, say **"I'm done."**
4. Your scores appear on the page.

(Or pick **⌨️ Type an answer** for the no-mic version.)

---

## Troubleshooting

- **`postgres://` vs `postgresql://`** — SQLAlchemy needs `postgresql://`. The app fixes
  the old scheme automatically, but make sure the string includes `?sslmode=require`.
- **CORS error / "Failed to fetch"** — `CORS_ORIGINS` on Render must be your **exact**
  Vercel URL, **no trailing slash**, and Render must have finished redeploying.
- **Backend slow on first request** — free Render sleeping; open `/health` first to wake it.
- **"voice interview is not configured" (503)** — the `LIVEKIT_*` keys aren't set on Render.
- **Voice connects but you hear silence** — the LiveKit keys on Render don't match the
  project your agent is connected to. They must be the **same** project.
- **Voice interview happens but no scores appear** — the agent's `REHEARSE_API_URL` isn't
  pointing at the same backend the website uses, or the agent isn't running.
- **Everything redeploys on push** — both Render and Vercel auto-deploy when you push to
  `main`.
