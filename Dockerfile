FROM python:3.12

# Setting environment variables for Python
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=off
ENV ALEMBIC_CONFIG=/usr/src/alembic/alembic.ini

# Installing dependencies
RUN apt update && apt install -y \
    gcc \
    libpq-dev \
    netcat-openbsd \
    postgresql-client \
    dos2unix \
    && apt clean

# Install Poetry
RUN python -m pip install --upgrade pip && \
    pip install poetry

# Copy dependency files
COPY ./poetry.lock /usr/src/poetry/poetry.lock
COPY ./pyproject.toml /usr/src/poetry/pyproject.toml
COPY ./alembic.ini /usr/src/alembic/alembic.ini

# Configure Poetry to avoid creating a virtual environment
RUN poetry config virtualenvs.create false

# Selecting a working directory
WORKDIR /usr/src/poetry

# Install dependencies with Poetry
RUN poetry lock
RUN poetry install --no-root

# Selecting a working directory
WORKDIR /usr/src/app

# Copy the source code
COPY ./app .

# Copy data folder
COPY ./data /usr/src/data

# Copy commands
COPY ./commands /commands

# Ensure Unix-style line endings for scripts
RUN dos2unix /commands/*.sh /commands/*.py || true

# Add execute bit to commands files
RUN chmod +x /commands/*.sh /commands/*.py || true

# Create symlink for easy CLI access
RUN ln -s /commands/import_events.py /usr/local/bin/import_events