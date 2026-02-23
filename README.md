# URL Shortener

A FastAPI-based URL shortener with async SQLAlchemy 2.0

![Tests](https://github.com/selimym/url-shortener/workflows/Tests/badge.svg)

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
│   ├── main.py              # FastAPI routes and dependency injection
│   ├── models.py            # SQLAlchemy models
│   ├── schemas.py           # Pydantic validation
│   ├── database.py          # Async database setup
│   ├── config.py            # Settings (Pydantic V2)
│   ├── keygen.py            # Random key generation
│   └── services/
│       └── url_service.py   # Business logic + data access
├── tests/
│   ├── conftest.py          # Test fixtures
│   ├── test_urls.py         # API endpoint tests
│   ├── test_service.py      # Service layer tests
│   ├── test_concurrency.py  # Race condition tests
│   ├── test_keygen.py       # Key generation tests
│   └── test_security.py     # Security tests
├── requirements.txt
└── pytest.ini
```

## Quick Start

```bash
# Setup
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run server
uvicorn shortener_app.main:app --reload
```

Visit http://localhost:8000/docs for interactive API docs.

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
```

## Design Goals

This project demonstrates:
- Handling race conditions in distributed systems
- Atomic operations for data consistency
- Clean service layer architecture
- Comprehensive testing strategies
- Async Python patterns with FastAPI + SQLAlchemy

## Contributing

This is a learning project. Feedback and suggestions welcome!