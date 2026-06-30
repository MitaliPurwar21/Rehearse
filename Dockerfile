# Backend (FastAPI) image. Render/Fly build this remotely — you don't need Docker locally.
FROM python:3.12-slim

WORKDIR /app

# Editable install keeps the source in place, so the judge can read its prompt/rubric
# files (eval/judge_prompt.md, eval/rubric.yaml) at runtime.
COPY . /app
RUN pip install --no-cache-dir -e ".[postgres]"

ENV JUDGE_PROVIDER=claude

# Hosts inject $PORT; default to 8000 for local `docker run`.
CMD ["sh", "-c", "uvicorn services.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
