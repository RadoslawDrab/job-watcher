FROM python:3.12-slim
RUN apt-get update && apt-get install -y ffmpeg imagemagick ghostscript && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY config.yml /app/config/config.yml
VOLUME ["/app/upload", "/app/output", "/app/logs", "/app/config"]

CMD ["python", "main.py"]