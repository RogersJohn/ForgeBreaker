# ForgeBreaker Architecture

## System Overview

ForgeBreaker is a 3-repository system for MTG Arena deck recommendations:

```
                                    +------------------+
                                    |   MTG Arena      |
                                    |   (Collection)   |
                                    +--------+---------+
                                             |
                                             v
+------------------+    REST     +------------------+    REST     +------------------+
|                  |------------>|                  |------------>|                  |
|   Frontend       |             |  ForgeBreaker    |             |   MLForge        |
|   (React)        |<------------|  (FastAPI)       |<------------|   (ONNX)         |
|                  |    JSON     |                  |    JSON     |                  |
+------------------+             +--------+---------+             +------------------+
                                          |
                                          | Anthropic API
                                          v
                                 +------------------+
                                 |   Claude AI      |
                                 |   (Tool Use)     |
                                 +------------------+
```

### Repository Responsibilities

| Repository | Purpose | Technology |
|------------|---------|------------|
| **ForgeBreaker** | MTG-specific logic: collection management, deck building, chat interface | Python/FastAPI |
| **MLForge** | Generic ONNX model serving platform | Python/FastAPI |
| **MCP-Demo** | REST-to-MCP gateway (optional) | Python |

## Backend Layers

```
+-----------------------------------------------------------------------+
|                              API Layer                                 |
|   /chat  /collection  /decks  /distance  /health                      |
+-----------------------------------------------------------------------+
                                    |
+-----------------------------------------------------------------------+
|                           Services Layer                               |
|   deck_builder  deck_improver  synergy_finder  collection_search       |
+-----------------------------------------------------------------------+
                                    |
+-----------------------------------------------------------------------+
|                           Analysis Layer                               |
|   distance.py  ranker.py  (deck scoring & ranking)                     |
+-----------------------------------------------------------------------+
                                    |
+-----------------------------------------------------------------------+
|                             ML Layer                                   |
|   inference.py (MLForge client)  features.py (feature extraction)      |
+-----------------------------------------------------------------------+
                                    |
+-----------------------------------------------------------------------+
|                            Data Layer                                  |
|   db/  (PostgreSQL)  parsers/  scrapers/  (external data)             |
+-----------------------------------------------------------------------+
```

## Module Responsibilities

### API Layer (`forgebreaker/api/`)

| Module | Endpoints | Purpose |
|--------|-----------|---------|
| `chat.py` | `POST /chat/` | Claude AI chat with MCP tools |
| `collection.py` | `POST /collection/import` | Import Arena collection |
| `decks.py` | `GET /decks/recommendations` | Get deck recommendations |
| `distance.py` | `GET /distance/{deck}` | Calculate collection-to-deck distance |
| `health.py` | `GET /health` | Health check |

### Services Layer (`forgebreaker/services/`)

| Module | Purpose |
|--------|---------|
| `deck_builder.py` | Build 60-card decks from collection around a theme |
| `deck_improver.py` | Analyze decks and suggest card swaps |
| `synergy_finder.py` | Find cards that work together mechanically |
| `collection_search.py` | Search collection by name, type, color, rarity |
| `card_database.py` | Load and query Scryfall card data |

### Analysis Layer (`forgebreaker/analysis/`)

| Module | Purpose |
|--------|---------|
| `distance.py` | Calculate completion % and wildcard costs for a deck |
| `ranker.py` | Rank decks by buildability, optionally using ML scoring |

### ML Layer (`forgebreaker/ml/`)

| Module | Purpose |
|--------|---------|
| `inference.py` | MLForge API client for deck scoring |
| `features.py` | Extract features for ML model input |
| `data/` | 17Lands data download and loading |
| `training/` | XGBoost model training and ONNX export |
| `deploy/` | Upload models to MLForge |

### MCP Tools (`forgebreaker/mcp/`)

| Tool | Purpose |
|------|---------|
| `search_collection` | Search user's cards by criteria |
| `build_deck` | Create a themed deck from collection |
| `find_synergies` | Find cards that work with a target card |
| `improve_deck` | Suggest upgrades for an existing deck |
| `export_to_arena` | Convert deck to Arena import format |
| `get_deck_recommendations` | Get ranked meta deck suggestions |
| `calculate_deck_distance` | Show missing cards for a deck |
| `list_meta_decks` | List available meta decks |
| `get_collection_stats` | Show collection statistics |

## Data Flows

### Chat Request Flow

```
User Message
     |
     v
POST /chat/
     |
     +---> Convert to Anthropic format
     |
     v
Claude API (claude-sonnet-4)
     |
     +---> If tool use requested:
     |          |
     |          v
     |     execute_tool()
     |          |
     |          +---> Load collection from DB
     |          |
     |          +---> Query card_db (Scryfall)
     |          |
     |          +---> Execute tool logic
     |          |
     |          v
     |     Return tool result to Claude
     |          |
     |          v
     |     (Loop up to 5 times)
     |
     v
Return assistant message
```

### Deck Recommendations Flow

```
GET /decks/recommendations?format=standard
     |
     v
get_deck_recommendations()
     |
     +---> Load user collection from DB
     |
     +---> Load meta decks for format
     |
     +---> For each deck:
     |          |
     |          +---> calculate_deck_distance()
     |          |          |
     |          |          +---> Count owned cards
     |          |          +---> Calculate missing cards
     |          |          +---> Sum wildcard costs
     |          |
     |          +---> extract_deck_features()
     |
     +---> Call MLForge /api/v1/score/batch
     |          |
     |          v
     |     MLForge ONNX inference
     |
     +---> Blend ML score (60%) with heuristic score (40%)
     |
     +---> Sort by final score
     |
     v
Return ranked recommendations
```

### Deck Building Flow

```
build_deck(theme="shrine")
     |
     +---> Search collection for theme matches
     |          |
     |          +---> Match card names
     |          +---> Match type lines
     |          +---> Match oracle text
     |
     +---> Determine deck colors from theme cards
     |
     +---> Detect archetype from keywords
     |
     +---> Select support cards:
     |          |
     |          +---> Fill removal slots
     |          +---> Fill card draw slots
     |          +---> Fill curve gaps
     |
     +---> Calculate mana base:
     |          |
     |          +---> Count color pips in deck
     |          +---> Proportional land distribution
     |
     v
Return BuiltDeck (60 cards)
```

### ML Training Pipeline

```
17Lands Public Data
     |
     v
download_17lands.py
     |
     +---> Download game data CSV
     |
     v
loader.py
     |
     +---> Validate schema
     +---> Filter to supported formats
     |
     v
engineer.py
     |
     +---> Extract 18 features per game
     +---> (deck composition, curve, colors, context)
     |
     v
train.py
     |
     +---> Split by draft_id (no leakage)
     +---> Train XGBoost classifier
     +---> Evaluate on holdout
     |
     v
export_to_onnx()
     |
     +---> Rename features to f0, f1, f2...
     +---> Convert to ONNX format
     |
     v
upload_model.py
     |
     +---> POST to MLForge /api/v1/models
     |
     v
MLForge serves model
```

## External Dependencies

### Runtime Services

| Service | URL | Purpose |
|---------|-----|---------|
| MLForge | `settings.mlforge_url` | ONNX model inference |
| Anthropic | Claude API | Chat AI with tool use |
| PostgreSQL | `settings.database_url` | Collection and deck storage |

### Data Sources

| Source | Purpose |
|--------|---------|
| 17Lands | Training data for win rate prediction |
| Scryfall | Card database (oracle text, types, colors, legality) |
| MTGGoldfish | Meta deck lists (scraped) |

## Configuration

Environment variables (via `pydantic-settings`):

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | `postgresql+asyncpg://localhost:5432/forgebreaker` | PostgreSQL connection |
| `MLFORGE_URL` | `https://backend-production-b2b8.up.railway.app` | MLForge API endpoint |
| `ANTHROPIC_API_KEY` | (required) | Claude API access |
| `DEBUG` | `false` | Enable debug mode |

## Deployment

Both ForgeBreaker and MLForge are deployed on Railway:

```
Railway Project
     |
     +---> ForgeBreaker Service
     |          |
     |          +---> Dockerfile (Python 3.11)
     |          +---> PostgreSQL (Railway addon)
     |
     +---> Frontend Service
     |          |
     |          +---> Dockerfile (Node.js)
     |          +---> Static build served by nginx
     |
     +---> MLForge Service (separate project)
              |
              +---> ONNX model storage
              +---> Inference API
```
