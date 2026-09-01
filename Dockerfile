# One image that serves the browser app and the API from a single process.
#
# Managed platforms give each service its own URL, so the two-container split in
# docker-compose.yml (nginx proxying /api to uvicorn) does not survive the move.
# Building the front end into the Python image sidesteps that entirely: one
# service, one origin, nothing to proxy and no CORS to configure.

# ---- build the browser app -------------------------------------------------
FROM node:20-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- serve it alongside the API --------------------------------------------
FROM python:3.12-slim
WORKDIR /srv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WEB_ROOT=/srv/static

# psycopg2-binary ships its own libpq, so there is no compiler to install here.
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
COPY --from=web /web/dist ./static

EXPOSE 8000

# Hosts pick the port and pass it in; 8000 is the local default.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
