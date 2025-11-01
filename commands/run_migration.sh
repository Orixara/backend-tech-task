#!/bin/bash
set -e

ALEMBIC_CONFIG="/usr/src/alembic/alembic.ini"
MIGRATIONS_DIR="/usr/src/app/database/migrations/versions"

echo "=== Starting Alembic Migration Process ==="

echo "Waiting for database..."
while ! nc -z $POSTGRES_HOST $POSTGRES_PORT; do
  sleep 0.1
done
echo "Database is ready!"

if [ ! -d "$MIGRATIONS_DIR" ]; then
    echo "Migrations folder does not exist. Creating it..."
    mkdir -p "$MIGRATIONS_DIR"
fi

export PGPASSWORD="$POSTGRES_PASSWORD"

if ! psql -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\dt" | grep -q "alembic_version"; then
    echo "Alembic version table not found. First time setup..."

    if [ -z "$(ls -A "$MIGRATIONS_DIR")" ]; then
        echo "No migration files found. Generating initial migration..."
        alembic -c $ALEMBIC_CONFIG revision --autogenerate -m "initial migration"
    fi

    echo "Applying all migrations..."
    alembic -c $ALEMBIC_CONFIG upgrade head
    echo "✓ Initial migration completed!"
    exit 0
fi

echo "Checking for database changes..."

if ! alembic -c $ALEMBIC_CONFIG revision --autogenerate -m "temp_migration"; then
    echo "Error generating migration. Exiting."
    exit 1
fi

LAST_MIGRATION=$(find "$MIGRATIONS_DIR" -type f -printf '%T+ %p\n' | sort | tail -n 1 | awk '{print $2}')

echo "Generated migration: $LAST_MIGRATION"

if grep -qE '^\s*pass\s*$' "$LAST_MIGRATION"; then
    echo "No changes detected. Deleting temporary migration."
    rm "$LAST_MIGRATION"
    echo "✓ Database is up to date!"
else
    echo "Changes detected. Applying migration..."
    alembic -c $ALEMBIC_CONFIG upgrade head
    echo "✓ Migration applied successfully!"
fi

echo "=== Migration Process Completed ==="