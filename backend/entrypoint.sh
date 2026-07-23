#!/bin/sh

# Wait for PostgreSQL to be ready using a python socket connection check
echo "Waiting for database to be ready..."
python3 -c "
import socket
import time
import os
import sys

host = 'db'
port = 5433
print(f'Checking connection to {host}:{port}...')
while True:
    try:
        with socket.create_connection((host, port), timeout=2):
            print('Database is online!')
            sys.exit(0)
    except (socket.error, socket.timeout):
        time.sleep(1)
"

# Run Alembic migrations
echo "Running database migrations..."
alembic upgrade head

# Start FastAPI application
echo "Starting FastAPI application..."
exec uvicorn main:app --host 0.0.0.0 --port 8000 --reload
