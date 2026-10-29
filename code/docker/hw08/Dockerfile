FROM python:3.12.13-slim
WORKDIR /app
COPY requirements*.txt ./
RUN pip install --no-cache-dir -r requirements-hw08.txt
COPY src ./src
COPY code ./code
COPY scripts ./scripts
ENV PYTHONPATH=/app:/app/code PYTHONUNBUFFERED=1
CMD ["python", "scripts/run_hw08_web.py"]
