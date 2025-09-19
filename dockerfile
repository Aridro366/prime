# Use official Python slim image
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

# Install system deps needed for ffmpeg and building PyNaCl (libsodium)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    build-essential \
    python3-dev \
    libffi-dev \
    libsodium-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy project files
COPY . /app

# Install Python dependencies
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Expose port for health check (Flask)
EXPOSE 8080

# Start the bot
CMD ["python", "main.py"]
