FROM python:3.12-slim AS base

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the sibling transcribing-module first so it can be installed as a dep.
COPY transcribing-module /opt/transcribing-module
RUN pip install --no-cache-dir /opt/transcribing-module

COPY DebateLens/transcribe-service /app
RUN pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1 \
    OUTPUT_DIR=/data/output \
    UPLOADS_DIR=/data/uploads \
    JOB_STORE_PATH=/data/output/jobs.json

EXPOSE 8080
CMD ["uvicorn", "transcribe_service.main:app", "--host", "0.0.0.0", "--port", "8080"]
