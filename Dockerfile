FROM python:3.10-slim

WORKDIR /app

# Install system deps first (important!)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=200 -r requirements.txt

COPY . .

COPY moti.sh /moti.sh
RUN chmod +x /moti.sh

EXPOSE 8000

# Ensure a default port
ENV PORT=8000

# Explicit gunicorn worker settings to avoid OOM
ENV GUNICORN_WORKERS=2
ENV GUNICORN_THREADS=2
ENV GUNICORN_TIMEOUT=120

ENTRYPOINT [ "/moti.sh" ]

# Use exec form (JSON array) for CMD
CMD ["gunicorn", "moti_backend.wsgi:application", \
    "--bind", "0.0.0.0:8000", \
    "--workers", "2", \
    "--threads", "2", \
    "--timeout", "120"]
