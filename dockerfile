# Dockerfile
FROM python:3.11-slim

# avoid Python buffering
ENV PYTHONUNBUFFERED=1

# Install ffmpeg dependencies and ffmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy files
COPY . /app

# Install python deps
RUN pip install --no-cache-dir -r requirements.txt

# Expose port for Render healthcheck (Flask app)
EXPOSE 8080

CMD ["python", "main.py"]