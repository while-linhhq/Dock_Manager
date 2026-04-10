#!/bin/bash
set -e

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL at ${POSTGRES_HOST}:${POSTGRES_PORT}..."
until python -c "
import psycopg2, os, sys
try:
    psycopg2.connect(
        host=os.environ['POSTGRES_HOST'],
        port=os.environ['POSTGRES_PORT'],
        dbname=os.environ['POSTGRES_DB'],
        user=os.environ['POSTGRES_USER'],
        password=os.environ['POSTGRES_PASSWORD'],
        connect_timeout=3
    ).close()
    sys.exit(0)
except Exception as e:
    print(f'DB not ready: {e}')
    sys.exit(1)
"; do
    sleep 2
done
echo "PostgreSQL is ready."

# Initialize database schema (idempotent)
echo "Running DB init..."
python -m app.db.init_db

# Start FastAPI server
echo "Starting uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8080 --workers 1
