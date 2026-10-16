# Stage 1: build the phone app as a website
FROM node:24-slim AS web
WORKDIR /mobile
COPY mobile/package.json mobile/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY mobile/ ./
RUN npx expo export --platform web

# Stage 2: the Python server, which also serves the website built above
FROM python:3.12-slim
WORKDIR /app
COPY server/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY server/ ./
COPY --from=web /mobile/dist ./web

# /data is a persistent volume on the host, so the database survives redeploys
ENV RETRACE_WEB_DIR=/app/web \
    RETRACE_DB_PATH=/data/retrace.db \
    PYTHONUNBUFFERED=1

# The host tells the server which port to use through $PORT
CMD ["sh", "-c", "fastapi run main.py --host 0.0.0.0 --port ${PORT:-8000}"]
