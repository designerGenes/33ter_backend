# NOTE: not all the below needs to be performed BY Docker, as it will copy scripts from the host machine to the container 
# for the container to run.
# This Docker container needs to create a setup that has all the tools necessary to: 
# 1. receive a video stream of a computer over ffmpeg and local wi-fi network
# 2. automatically take screenshots of the video stream and save them to a local folder, and delete any screenshots older than 5 minutes 
# 3. Run a docker container inside itself that, upon a hardware button being pressed, will send the most recent screenshot to an on-premise Azure Cognitive Service for OCR (information can be found on this at https://learn.microsoft.com/en-us/azure/ai-services/cognitive-services-container-support)
# 4. The OCR results will be returned to the Docker container, at which point it should send the results to the OpenAI ChatGPT API, along with specific instructions
# 5. The ChatGPT API will return a response, which will be sent to a screen connected to the Raspberry Pi via HDMI

#!/bin/bash
FROM --platform=$TARGETPLATFORM debian:bullseye-slim

# Set bash as the default shell
SHELL ["/bin/bash", "-c"]

# Set build arguments and environment variables for multi-platform support
ARG TARGETPLATFORM
ARG BUILDPLATFORM
RUN echo "I am running on $BUILDPLATFORM, building for $TARGETPLATFORM"

# open any necessary ports for SSH into the container
EXPOSE 22 8765

# Install dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-dev \
    i2c-tools \
    ffmpeg \
    bash \
    iproute2 \
    iputils-ping \
    net-tools \
    curl \
    wget \
    && ln -sf /bin/bash /bin/sh \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Remove RPi specific packages since we're on Mac
# Install Docker CLI only (not daemon)
RUN apt-get update && apt-get install -y \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    procps \
    vim \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null \
    && apt-get update \
    && apt-get install -y docker-ce-cli

RUN pip3 install --upgrade pip
RUN pip3 install azure-ai-vision-imageanalysis aiohttp python-dotenv openai rich websockets asyncio python-socketio

# Create directories first
RUN mkdir -p /app/scripts /app/screenshots /app/logs

# Set the working directory
WORKDIR /app

# Copy only the scripts and requirements
COPY scripts/*.py /app/scripts/
COPY requirements.txt /app/scripts/

# Remove the auto-generated main.py since we're providing our own
COPY scripts/main.py /app/scripts/main.py
RUN chmod +x /app/scripts/main.py

# Install any needed packages specified in requirements.txt
# RUN pip3 install --no-cache-dir -r /app/scripts/requirements.txt

# set up any networking that needs to be done
# set up the ffmpeg stream
# set up the hardware button
# set up the screen
# set up the Azure Cognitive Service
# set up the OpenAI ChatGPT API

# Add a healthcheck
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD ps aux | grep python3 || exit 1

# Update entrypoint script (remove env loading since docker-compose handles it)
COPY <<EOF /app/scripts/entrypoint.sh
#!/bin/bash
exec python3 /app/scripts/main.py 2>&1 | tee /app/logs/container.log
EOF

RUN chmod +x /app/scripts/entrypoint.sh

# Change CMD to use entrypoint script
CMD ["/app/scripts/entrypoint.sh"]






