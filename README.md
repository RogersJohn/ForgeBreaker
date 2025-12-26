# ForgeBreaker

MTG Arena collection manager that suggests decks based on owned cards, using ML-powered recommendations.

## Why ForgeBreaker?

Building competitive decks in MTG Arena is frustrating:

- **Wildcards are precious** - You don't want to spend rare wildcards on a deck you can't finish
- **Meta decks require cards you don't own** - Most deck sites assume you have everything
- **No visibility into what's buildable** - Arena doesn't show which meta decks match your collection

ForgeBreaker solves this by analyzing your collection and ranking meta decks by how close you are to completing them. It uses ML-powered recommendations to surface decks you can actually build, not just what's theoretically best.

## Features

- Import your Arena collection via text export
- Browse competitive meta decks from MTGGoldfish
- See how close you are to completing each deck
- **ML-powered deck recommendations** blending collection analysis with [MLForge scoring](docs/MODEL_CARD.md)
- Get recommendations based on your wildcard budget
- AI-powered deck advice via Claude with MCP tool calling

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed system design.

ForgeBreaker integrates with MLForge for ML-based deck recommendations:

```
User Query → ForgeBreaker API
                ↓
         Load Collection (PostgreSQL)
                ↓
         Load Meta Decks (MTGGoldfish)
                ↓
         Extract Features (DeckFeatures)
                ↓
         Call MLForge API (batch scoring)
                ↓
         Blend ML Score (60%) + Heuristics (40%)
                ↓
         Return Ranked Recommendations
```

**Data Flow:**
1. User requests deck recommendations via `/chat` endpoint (using MCP tool calling)
2. ForgeBreaker loads collection and available meta decks from database
3. For each deck, extracts ML features: completion %, wildcard costs, archetype, win rate
4. Sends batch feature request to MLForge (`/api/v1/score/batch`)
5. MLForge returns ML confidence scores for each deck
6. Blends ML score (weighted by confidence) with heuristic score
7. Returns ranked deck recommendations with `scoring_method: "ml_blended"`

**Graceful Fallback:** If MLForge is unavailable, automatically falls back to heuristic-only scoring.

## Tech Stack

- **Backend**: Python 3.11+ / FastAPI
- **Frontend**: React 18 / TypeScript / Tailwind CSS
- **Database**: PostgreSQL (async via SQLAlchemy 2.0)
- **ML**: MLForge API for recommendation scoring
- **LLM**: Claude API with MCP tool calling

## Development

### Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL 15+

### Backend Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install dependencies
pip install -e ".[dev]"

# Set environment variables
export DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/forgebreaker"
export ANTHROPIC_API_KEY="your-api-key"

# Run linting
ruff check .
ruff format --check .

# Run type checking
mypy forgebreaker

# Run tests (requires 70% coverage)
pytest

# Expected output:
# ============================= test session starts ==============================
# collected 422 items
# ...
# ============================= 422 passed in 45.23s ==============================
# TOTAL                                                        83%

# Start dev server
uvicorn forgebreaker.main:app --reload
```

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start dev server
npm run dev

# Build for production
npm run build
```

## API Endpoints

### Health

- `GET /health` - Health check
- `GET /ready` - Readiness check

### Collection

- `GET /collection/{user_id}` - Get user's collection stats
- `POST /collection/{user_id}` - Import Arena collection (body: `{"arena_export": "..."}`)

### Decks

- `GET /decks/{format}` - List meta decks for format
- `GET /decks/{format}/{deck_name}` - Get specific deck

### Distance

- `GET /distance/{user_id}/{format}/{deck_name}` - Calculate collection distance to deck

### Chat

- `POST /chat/` - Send chat message (body: `{"user_id": "...", "messages": [...]}`)

## Example API Usage

### Import a Collection

```bash
curl -X POST http://localhost:8000/collection/user123/import \
  -H "Content-Type: application/json" \
  -d '{
    "text": "4 Lightning Bolt\n4 Monastery Swiftspear\n20 Mountain",
    "format": "auto"
  }'
```

Response:
```json
{
  "user_id": "user123",
  "cards_imported": 3,
  "total_cards": 28,
  "cards": {
    "Lightning Bolt": 4,
    "Monastery Swiftspear": 4,
    "Mountain": 20
  }
}
```

### Get Meta Decks

```bash
curl http://localhost:8000/decks/standard
```

Response:
```json
{
  "format": "standard",
  "decks": [
    {
      "name": "Mono Red Aggro",
      "archetype": "Aggro",
      "format": "standard",
      "win_rate": 0.54,
      "meta_share": 0.12
    }
  ],
  "count": 1
}
```

### Calculate Deck Distance

```bash
curl http://localhost:8000/distance/user123/standard/Mono%20Red%20Aggro
```

Response:
```json
{
  "deck_name": "Mono Red Aggro",
  "deck_format": "standard",
  "owned_cards": 24,
  "missing_cards": 16,
  "total_cards": 40,
  "completion_percentage": 0.6,
  "is_complete": false,
  "wildcard_cost": {
    "common": 0,
    "uncommon": 4,
    "rare": 8,
    "mythic": 4,
    "total": 16
  }
}
```

### Chat with Claude

```bash
curl -X POST http://localhost:8000/chat/ \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user123",
    "messages": [{"role": "user", "content": "What meta decks can I build?"}]
  }'
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://localhost:5432/forgebreaker` |
| `ANTHROPIC_API_KEY` | Claude API key | (required for chat) |
| `MLFORGE_URL` | MLForge API endpoint | `https://backend-production-b2b8.up.railway.app` |
| `DEBUG` | Enable debug mode | `false` |

## Deployment

The app is configured for Railway deployment:

- `railway.toml` - Railway configuration
- `Procfile` - Process definition
- `runtime.txt` - Python version

### Deploy to Railway

1. Connect your GitHub repo to Railway
2. Set environment variables in Railway dashboard
3. Deploy

## Project Structure

```
forgebreaker/
├── api/           # FastAPI routers
├── analysis/      # Deck distance/ranking
├── db/            # Database operations
├── jobs/          # Scheduled jobs
├── mcp/           # MCP tool definitions
├── ml/            # ML feature engineering
├── models/        # Domain models
├── parsers/       # Arena export/Scryfall parsers
└── scrapers/      # MTGGoldfish scraper

frontend/
├── src/
│   ├── api/       # API client
│   ├── components/# React components
│   └── hooks/     # React Query hooks
```

## License

MIT
