FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl \
    mkosi systemd-container debootstrap \
    xorriso squashfs-tools mtools dosfstools \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
