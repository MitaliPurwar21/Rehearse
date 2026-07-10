# Two stages: build a venv with all the deps, then copy it into a slim runtime that
# runs as a non-root user. One image covers three roles (the API, the operator, and the
# eval Job it launches) depending on the command, so the whole system ships from one build.
FROM python:3.12-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY . /app
# Editable install so eval/ keeps its prompt, rubric and frozen judgements right next to
# the code at runtime. postgres = the psycopg2 driver; operator = kopf + the k8s client.
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install -e ".[postgres,operator]"

FROM python:3.12-slim AS runtime
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    JUDGE_PROVIDER=claude
# Drop root. The app owns its files but runs unprivileged. Reference the user by its
# numeric uid so Kubernetes can verify it's non-root without guessing from a name.
RUN useradd --create-home --uid 1000 app
WORKDIR /app
COPY --from=build /opt/venv /opt/venv
COPY --from=build /app /app
RUN chown -R app:app /app
USER 1000
EXPOSE 8000
# Hosts inject $PORT; default to 8000 for a local `docker run`. The operator Deployment
# and the eval Job override this (kopf run ... / python -m eval.emit_agreement).
CMD ["sh", "-c", "uvicorn services.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
