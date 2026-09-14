FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY code/web_application/ ./web_application/
WORKDIR /app/web_application

EXPOSE 8702

# One worker owns the in-memory store; publish locally with 127.0.0.1:8702:8702.
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8702", "--workers", "1"]
