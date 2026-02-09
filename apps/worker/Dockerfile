FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY worker.py ./worker.py
COPY tasks.py ./tasks.py
COPY services ./services

CMD ["python", "worker.py"]
