# ForgeBreaker

MTG Arena collection manager that suggests decks based on owned cards.

## Features

- Import your Arena collection via text export
- Browse competitive meta decks
- See how close you are to completing each deck
- Get deck recommendations based on your wildcards budget
- AI-powered deck advice via Claude

## Tech Stack

- **Backend**: Python 3.11+ / FastAPI
- **Frontend**: React 18 / TypeScript / Tailwind
- **Database**: PostgreSQL
- **ML**: MLForge API integration
- **LLM**: Claude API

## Development

```bash
# Install dependencies
pip install -e ".[dev]"

# Run linting
ruff check .
ruff format --check .

# Run type checking
mypy forgebreaker

# Run tests
pytest

# Start dev server
uvicorn forgebreaker.main:app --reload
```

## API Endpoints

- `GET /health` - Health check
- `GET /ready` - Readiness check

## License

MIT
