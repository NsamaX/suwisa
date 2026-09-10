FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    OMP_THREAD_LIMIT=1 DATABASE_PATH=/app/data/suwisa.sqlite3

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-tha tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 suwisa \
    && useradd --uid 1000 --gid suwisa --create-home suwisa

WORKDIR /app
COPY requirements.lock pyproject.toml README.md ./
COPY src ./src
RUN pip install -r requirements.lock \
    && pip install --no-deps . \
    && mkdir /app/data /app/backups \
    && chown suwisa:suwisa /app/data /app/backups

USER suwisa
CMD ["python", "-m", "suwisa"]
