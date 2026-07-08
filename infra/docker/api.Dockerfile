# ProcessIQ control-plane API + web UI. Lean image (no GPU / heavy ML): real SOP generation
# runs through the hosted Gemini VLM. Multi-stage, slim, non-root.
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

FROM base AS deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM deps AS runtime
# Application code (everything the API imports at runtime).
COPY processiq_shared ./processiq_shared
COPY agents ./agents
COPY services ./services
COPY apps ./apps
# Non-root user + writable runtime dirs (uploaded screenshots, cache).
RUN useradd -m appuser \
 && mkdir -p /app/objstore_data /app/.cache \
 && chown -R appuser /app
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/v1/health').status==200 else 1)"
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
