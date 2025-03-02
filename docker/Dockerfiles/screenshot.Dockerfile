FROM python:3.11-slim

WORKDIR /app

# Install system dependencies including X11 and screenshot dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3-tk \
    python3-dev \
    xvfb \
    x11-utils \
    scrot \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p config logs screenshots temp

# Set environment variables
ENV PYTHONPATH=/app
ENV RUN_MODE=container
ENV DISPLAY=:99

# Create entrypoint script to start Xvfb and the screenshot service
RUN echo '#!/bin/bash\nXvfb :99 -screen 0 1024x768x16 &\nsleep 1\npython3 core/screenshot_recorder.py' > /entrypoint.sh \
    && chmod +x /entrypoint.sh

# Start the screenshot service
CMD ["/entrypoint.sh"]