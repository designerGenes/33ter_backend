FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p config logs

# Set environment variables
ENV PYTHONPATH=/app
ENV RUN_MODE=container

# Expose the Socket.IO port
EXPOSE 5348

# Start the Socket.IO server
CMD ["python3", "socket/socketio_server.py"]