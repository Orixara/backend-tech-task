# Event Analytics System

Система збору та аналізу подій з підтримкою Hot/Cold Storage (PostgreSQL + DuckDB).


## Як запустити

### Вимоги
- Docker 20.10+
- Docker Compose 2.0+

### Запуск
```bash
# 1. Створити .env файл
cp .env.sample .env

# 2. Запустити всю інфраструктуру
docker-compose up --build

# 3. Перевірити статус
docker-compose ps
```

API буде доступний на `http://localhost:8000`

Документація: `http://localhost:8000/docs`

## Тестування
```bash
# Запуск всіх тестів
docker-compose run --rm web pytest

# Запуск з coverage
docker-compose run --rm web pytest --cov=app

# Конкретний тест
pytest app/tests/integration/test_analytics_endpoints.py


## Benchmark результати

### Конфігурація
- 100,000 подій
- Batch size: 1,000 events

### Event Ingestion
Total time: 7.01 seconds
Throughput: 14,265 events/sec
Average latency: 66ms per batch
Min latency: 43ms
Max latency: 187ms

### Analytics Queries
DAU query: 3,714ms (30-денний діапазон)
Top Events query: 699ms
Retention query: 1,555ms


## Технології

- FastAPI, Python 3.12
- PostgreSQL 16 (hot storage)
- DuckDB (cold storage)
- Redis (queue + rate limiting)
- Docker & Docker Compose

## Що не встиг
- Зробити rate limiting
- Покрити все тестами
