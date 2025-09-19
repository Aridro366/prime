# Use official Python 3.12 image
FROM python:3.12-slim

# --------------------
# Environment variables
# --------------------
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

# --------------------
# Install system dependencies
# --------------------
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    build-essential \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# --------------------
# Set workdir
# --------------------
WORKDIR /app

# --------------------
# Copy files
# --------------------
COPY . /app

# --------------------
# Install Python dependencies
# --------------------
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# --------------------
# Expose port for Flask keep-alive
# --------------------
EXPOSE 8080

# --------------------
# Start bot
# --------------------
CMD ["python", "main.py"]