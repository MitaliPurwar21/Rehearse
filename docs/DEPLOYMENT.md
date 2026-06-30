# Deployment

Backend (FastAPI) on **Render**, frontend (Next.js) on **Vercel**. Both have free tiers.
Render builds the Docker image for you, so you don't need Docker locally.

There's a small chicken-and-egg: the frontend needs the backend's URL, and the backend's
CORS needs the frontend's URL. So: deploy the backend first, deploy the frontend pointed
at it, then update the backend's `CORS_ORIGINS` with the frontend URL.

## 1. Backend → Render

1. Push to GitHub (already done).
2. In Render: **New → Blueprint**, select this repo. It reads `render.yaml` and creates the
   `rehearse-api` web service (Docker).
3. Set the secrets it asks for (these are `sync: false` in the blueprint):
   - `ANTHROPIC_API_KEY` — your Claude key.
   - `CORS_ORIGINS` — leave as `http://localhost:3000` for now; update in step 3.
   - `DATABASE_URL` — optional. Omit to use SQLite (simplest; data resets on redeploy on
     the free tier). For persistence, create a free Postgres at [neon.tech](https://neon.tech)
     and paste its `postgresql://...` URL here.
4. Deploy. When it's live, copy the URL (e.g. `https://rehearse-api.onrender.com`) and
   check `https://rehearse-api.onrender.com/health` returns `{"status":"ok"}`.

> Free-tier note: the service sleeps after ~15 min idle, so the first request after a nap
> takes ~30s to wake. Fine for a demo.

## 2. Frontend → Vercel

1. In Vercel: **Add New → Project**, import this repo.
2. Set **Root Directory** to `apps/web` (so Vercel builds only the frontend).
3. Add an environment variable:
   - `NEXT_PUBLIC_API_URL` = your Render backend URL from step 1.
4. Deploy. Copy the frontend URL (e.g. `https://rehearse.vercel.app`).

## 3. Close the loop (CORS)

Back in Render, set `CORS_ORIGINS` to your Vercel URL (comma-separated if you want more):

```
CORS_ORIGINS=https://rehearse.vercel.app,http://localhost:3000
```

Save — Render redeploys. Now open the Vercel URL and run the full flow in the browser.

## Updating

Both platforms redeploy automatically on every push to `main`.
