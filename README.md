# Functional Requirements

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
├── shortener_app/           \# Main application package
│   ├── __init__.py
│   ├── main.py             \# FastAPI app and routes
│   ├── crud.py             \# Database operations
│   ├── models.py           \# SQLAlchemy models
│   ├── schemas.py          \# Pydantic schemas
│   ├── database.py         \# Database configuration
│   ├── config.py           \# Settings management
│   └── keygen.py           \# Random key generation
├── tests/                   \# Test suite
│   ├── conftest.py         \# Test fixtures
│   ├── test_urls.py        \# API endpoint tests
│   ├── test_crud.py        \# CRUD operation tests
│   └── test_keygen.py      \# Key generation tests
├── .github/
│   └── workflows/
│       └── tests.yml       \# CI workflow
├── .env.example            \# Example environment variables
├── pytest.ini              \# Pytest configuration
├── requirements.txt        \# Project dependencies
└── README.md

```

## Quick Start

```

# Create virtual environment

python -m venv venv
source venv/bin/activate  \# On Windows: venv\Scripts\activate

# Install dependencies

pip install -r requirements.txt

# Create .env file

cp .env.example .env

# Run the server

uvicorn shortener_app.main:app --reload

```

Visit http://localhost:8000/docs for the interactive API documentation.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Welcome message |
| `/url` | POST | Create shortened URL |
| `/{url_key}` | GET | Redirect to target URL |
| `/admin/{secret_key}` | GET | View URL statistics |
| `/admin/{secret_key}` | DELETE | Deactivate shortened URL |

## Configuration

Environment variables can be set in `.env` file:

```

ENV_NAME="Development"
BASE_URL="http://localhost:8000"
DB_URL="sqlite+aiosqlite:///./shortener.db"

```

## Contributing

This is a learning project, but suggestions and feedback are welcome! Feel free to open an issue or submit a pull request.