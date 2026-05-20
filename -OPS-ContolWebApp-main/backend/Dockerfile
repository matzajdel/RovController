FROM ros:humble-ros-base

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=2137 \
    ROS_DOMAIN_ID=0

WORKDIR /app/backend

# System CLI and ROS packages used by backend runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    python3-venv \
    openssh-client \
    sshpass \
    screen \
    bluez \
    v4l-utils \
    gstreamer1.0-tools \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav \
    procps \
    curl \
    ros-humble-cv-bridge \
    ros-humble-geometry-msgs \
    ros-humble-rosbridge-server \
    ros-humble-sensor-msgs \
    ros-humble-std-msgs \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements-docker.txt /tmp/requirements-docker.txt
RUN python3 -m pip install --no-cache-dir --upgrade pip \
    && python3 -m pip install --no-cache-dir -r /tmp/requirements-docker.txt

COPY backend/ /app/backend/

EXPOSE 2137

CMD ["bash", "-lc", "./start_backend.sh"]
