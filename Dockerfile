# Backend API (FastAPI). Installs the package + deps, runs migrations, then serves.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# Dependencies first, in their own cached layer: a stub package lets `pip install .`
# resolve pyproject's dependencies without the source, so code edits don't re-download
# every package on each rebuild.
COPY pyproject.toml ./
RUN mkdir -p app && touch app/__init__.py && pip install . && pip uninstall -y bria-api

COPY . .
RUN pip install --no-deps .

EXPOSE 8000
# Apply DB migrations, optionally load the demo company (only when SEED_DEMO=true, and
# only once — a failure there never blocks the API), then start the server. Bind to $PORT
# when the platform injects one (Render/Railway), else default to 8000 for docker-compose.
CMD ["sh", "-c", "alembic upgrade head && (python scripts/bootstrap_demo.py || echo 'bootstrap_demo: fallo, la API arranca igual') && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
