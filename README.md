# URL Shortener

A FastAPI-based URL shortener with async SQLAlchemy 2.0

**Features:**
- Fast async FastAPI with SQLAlchemy 2.0
- PostgreSQL + Redis (Docker) or SQLite (local dev)
- Race condition handling with atomic operations
- Redis-backed rate limiting (configurable per endpoint)
- Alembic database migrations
- Full Docker Compose setup with health checks
- Comprehensive test suite (9 concurrency tests + integration tests)

## Core Requirements

- **URL Shortening:** Users should be able to input a long URL and receive a unique, shortened alias. The shortened URL should use a compact format with English letters and digits to save space and ensure uniqueness.  
- **URL Redirection:** When users access a shortened URL, the service should redirect them seamlessly to the original URL with minimal delay.  
- **Link Analytics:** The system should be able to track the number of times each shortened URL is accessed to provide insights into link usage.

## Scale Requirements

- **100M Daily Active Users**  
- **Read:write ratio:** 100:1  
- **Write volume:** ~1 million write requests per day  
- **Entry size:** ~500 bytes per record


## Project Structure

```
url-shortener/
├── shortener_app/
│   ├── main.py                      # FastAPI routes and dependency injection
│   ├── models.py                    # SQLAlchemy models
│   ├── schemas.py                   # Pydantic validation
│   ├── database.py                  # Async database setup
│   ├── config.py                    # Settings (Pydantic V2)
│   ├── keygen.py                    # Random key generation
│   ├── services/
│   │   └── url_service.py           # Business logic + data access
│   └── infrastructure/
│       ├── redis_client.py          # Redis connection management
│       └── rate_limiter.py          # Rate limiting logic
├── alembic/
│   ├── versions/                    # Database migration scripts
│   └── env.py                       # Alembic configuration
├── tests/
│   ├── conftest.py                  # Test fixtures
│   ├── test_urls.py                 # API endpoint tests
│   ├── test_service.py              # Service layer tests
│   ├── test_concurrency.py          # Race condition tests (9 tests)
│   ├── test_keygen.py               # Key generation tests
│   └── test_security.py             # Security tests
├── Dockerfile                       # Container image definition
├── docker-compose.yml               # Multi-service orchestration
├── docker-compose.override.yml.example  # Local dev customizations
├── .env.development.example         # Dev environment template
├── .env.production.example          # Prod environment template
├── alembic.ini                      # Alembic migrations config
├── requirements.txt                 # Python dependencies
└── pytest.ini                       # Pytest configuration
```

## Quick Start

### Option 1: Local Development (SQLite)

```bash
# Setup
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run server
uvicorn shortener_app.main:app --reload
```

Visit http://localhost:8000/docs for interactive API docs.

### Option 2: Docker (PostgreSQL + Redis)

```bash
# Quick start with defaults
docker-compose up --build

# Visit http://localhost:8000/docs
```

See **Docker Setup** section below for detailed instructions.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Welcome message |
| `/url` | POST | Create shortened URL |
| `/{url_key}` | GET | Redirect to target URL (increments clicks) |
| `/admin/{secret_key}` | GET | View URL statistics |
| `/admin/{secret_key}` | DELETE | Deactivate shortened URL |

## Configuration

Environment variables (`.env`):

```env
ENV_NAME="Development"
BASE_URL="http://localhost:8000"
DB_URL="sqlite+aiosqlite:///./shortener.db"
REDIS_URL="redis://localhost:6379/0"
RATE_LIMIT_ENABLED="false"
USE_MIGRATIONS="false"
```

## Docker Setup

This project includes full Docker containerization with PostgreSQL, Redis, and automated migrations.

### Architecture

The Docker setup includes three services:
- **web**: FastAPI application (port 8000)
- **postgres**: PostgreSQL 15 database (persistent volume)
- **redis**: Redis 7 for rate limiting

### Development Environment

**Quick start** (uses safe default credentials):

```bash
# Start all services
docker-compose up --build

# Stop services
docker-compose down

# Stop and remove volumes (clean slate)
docker-compose down -v
```

**Default credentials** (safe for local dev):
- PostgreSQL: `urlshortener:devpassword123`
- These are NOT committed in `.env` files, only in `docker-compose.yml` defaults

**Customize for local development**:

```bash
# Copy the override template
cp docker-compose.override.yml.example docker-compose.override.yml

# Edit with your preferences (this file is gitignored)
vim docker-compose.override.yml
```

Example `docker-compose.override.yml`:
```yaml
version: '3.8'

services:
  postgres:
    environment:
      POSTGRES_PASSWORD: my-local-password
    ports:
      - "5432:5432"  # Expose for debugging

  web:
    environment:
      RATE_LIMIT_ENABLED: "false"  # Disable rate limiting locally
    volumes:
      - ./shortener_app:/app/shortener_app  # Live code reload
```

### Production Environment

**Using environment variables** (recommended):

```bash
# Set secure credentials
export POSTGRES_USER="urlshortener"
export POSTGRES_PASSWORD="$(openssl rand -base64 32)"
export POSTGRES_DB="urlshortener"
export BASE_URL="https://your-domain.com"

# Start services
docker-compose up -d
```

**Using .env file**:

```bash
# Create production environment file (gitignored)
cp .env.production.example .env.production

# Edit with real credentials
vim .env.production

# IMPORTANT: Use strong passwords!
# Generate: openssl rand -base64 32
```

Example `.env.production`:
```env
ENV_NAME="Production"
BASE_URL="https://your-domain.com"
POSTGRES_USER="urlshortener"
POSTGRES_PASSWORD="your-super-secure-random-password-here"
POSTGRES_DB="urlshortener"
REDIS_URL="redis://redis:6379/0"
USE_MIGRATIONS="true"
RATE_LIMIT_ENABLED="true"
RATE_LIMIT_CREATE=10
RATE_LIMIT_READ=100
```

Then start:
```bash
docker-compose --env-file .env.production up -d
```

### Docker Commands Cheat Sheet

```bash
# View logs
docker-compose logs web
docker-compose logs -f web  # Follow logs

# Check service health
docker-compose ps

# Run migrations manually
docker-compose exec web alembic upgrade head

# Access PostgreSQL CLI
docker-compose exec postgres psql -U urlshortener -d urlshortener

# Access Redis CLI
docker-compose exec redis redis-cli

# Run tests in container
docker-compose exec web pytest tests/

# Rebuild after dependency changes
docker-compose up --build

# Clean everything (including volumes)
docker-compose down -v
docker system prune -a
```

### Security Best Practices

**For Learning/Development**:
- Default credentials in `docker-compose.yml` are safe (local only, not exposed)
- Safe to commit to public GitHub repos

**For Production**:
- **NEVER** commit real credentials to git
- Use **environment variables** or **secrets managers** (AWS Secrets Manager, HashiCorp Vault)
- Use **strong random passwords**: `openssl rand -base64 32`
- Enable **TLS/SSL** for all connections
- Use **managed databases** (AWS RDS, Google Cloud SQL) with encrypted connections
- Rotate credentials regularly
- Use **docker secrets** for swarm deployments

### Database Migrations

Migrations run automatically on container startup. Manual control:

```bash
# Check current migration
docker-compose exec web alembic current

# View migration history
docker-compose exec web alembic history

# Upgrade to latest
docker-compose exec web alembic upgrade head

# Rollback one version
docker-compose exec web alembic downgrade -1

# Create new migration
docker-compose exec web alembic revision --autogenerate -m "description"
```

### Testing

Run tests against Docker services:

```bash
# All tests (uses SQLite for speed)
docker-compose exec web pytest tests/ -v

# Concurrency tests only
docker-compose exec web pytest tests/test_concurrency.py -v

# With coverage
docker-compose exec web pytest tests/ --cov=shortener_app
```

Or run tests locally while Docker services are running:

```bash
# Start only PostgreSQL and Redis
docker-compose up postgres redis -d

# Run tests from local venv (configure DB_URL if needed)
pytest tests/ -v
```

## Design Goals

This project demonstrates:
- **Concurrency handling**: Atomic operations, race condition prevention (9 concurrency tests)
- **Clean architecture**: Service layer pattern separating business logic from data access
- **Production patterns**: Docker containerization, database migrations, rate limiting
- **Testing strategies**: Comprehensive test coverage with pytest (SQLite for tests, PostgreSQL for production)
- **Async patterns**: FastAPI + SQLAlchemy async throughout

## Contributing

This is a learning project. Feedback and suggestions welcome!