# ForgeBreaker - Claude Code Guidelines

## Project Context

MTG Arena collection manager that suggests decks based on owned cards.

- **Backend**: Python 3.11+ / FastAPI
- **Frontend**: React 18 / TypeScript / Tailwind
- **Database**: PostgreSQL
- **ML**: Calls MLForge API (already deployed)
- **LLM**: Claude API via MCP tool patterns
- **Deployment**: Railway
- **Repo**: github.com/JohnRogers-Code-projects/ForgeBreaker

---

## Workflow Rules

### PR Requirements

- **Max 300 lines changed** (excluding tests)
- **Single logical component** per PR
- **Tests included** in same PR
- **All checks must pass** before requesting review

### What Claude Does Automatically

- Create feature branches
- Write code and tests
- Commit with conventional commit messages
- Push branches
- Create draft PRs
- Request Copilot review
- Fetch and summarize Copilot feedback
- Fix blocking issues and re-request review

### What Requires Human Approval

- Merging PRs
- Marking PRs as ready (non-draft)
- Architectural changes not in spec
- Adding unplanned dependencies

### After Each PR

1. Create draft PR
2. Request Copilot review
3. Summarize review for human
4. Wait for human to approve merge
5. After merge confirmed, proceed to next PR

---

## Code Standards

### No Sycophancy

Don't praise code. "Done" or "This works" is sufficient.

### Architecture First

Before implementing, state:
- Problem being solved
- Approach chosen
- Tradeoffs accepted

### Code Quality Flags

```python
# DEBT: <description> - <suggested fix>
# PERF: <concern> - <impact>
# SECURITY: <concern> - <severity: LOW/MED/HIGH>
# TODO: <task>
```

### Function Limits

- Max 50 lines per function
- Max 3 levels of nesting
- Max 300 lines per file

### Required Comments

Inline comments mandatory for:
- Regex patterns (explain what they match)
- SQL with joins
- O(n²)+ algorithms
- Bitwise operations

### Testing Standards

- At least one edge case per function
- Include failure cases
- Use real MTG card names in test data
- Tests must be fast (<100ms each)

---

## Dependencies

### Pre-Approved (no justification needed)

**Backend:**
- fastapi, uvicorn[standard], pydantic, pydantic-settings
- httpx, sqlalchemy[asyncio], asyncpg, alembic
- pytest, pytest-asyncio, pytest-cov
- ruff, mypy

**Frontend:**
- react, react-dom, typescript
- tailwindcss, @tailwindcss/forms
- @tanstack/react-query
- vite

**Tools:**
- gh (GitHub CLI)

### Requires Justification

Any dependency not listed above.

---

## File Structure

```
forgebreaker/
├── __init__.py
├── main.py              # FastAPI app entry
├── config.py            # Settings via pydantic-settings
├── models/
│   ├── __init__.py
│   ├── card.py          # Card dataclass
│   ├── collection.py    # Collection dataclass
│   ├── deck.py          # MetaDeck, DeckDistance, RankedDeck
│   └── db.py            # SQLAlchemy models
├── parsers/
│   ├── __init__.py
│   ├── arena_export.py  # Parse Arena text export
│   └── scryfall.py      # Load Scryfall bulk data
├── scrapers/
│   ├── __init__.py
│   └── mtggoldfish.py   # Scrape meta decks
├── analysis/
│   ├── __init__.py
│   ├── distance.py      # Deck distance calculation
│   └── ranker.py        # Deck ranking algorithm
├── ml/
│   ├── __init__.py
│   ├── features.py      # Feature engineering
│   └── inference.py     # MLForge client
├── mcp/
│   ├── __init__.py
│   └── tools.py         # MCP tool definitions
├── api/
│   ├── __init__.py
│   ├── collection.py    # Collection endpoints
│   ├── decks.py         # Deck endpoints
│   └── chat.py          # Chat endpoint
├── db/
│   ├── __init__.py
│   ├── database.py      # Engine, session
│   └── operations.py    # CRUD operations
└── jobs/
    ├── __init__.py
    └── update_meta.py   # Scheduled meta refresh

frontend/
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── api/
│   │   └── client.ts    # API client
│   ├── components/
│   │   ├── CollectionImporter.tsx
│   │   ├── DeckBrowser.tsx
│   │   ├── DeckCard.tsx
│   │   ├── DeckDetail.tsx
│   │   └── ChatAdvisor.tsx
│   └── hooks/
│       └── useCollection.ts
├── index.html
├── package.json
├── tsconfig.json
├── tailwind.config.js
└── vite.config.ts

tests/
├── conftest.py
├── test_models.py
├── test_parsers.py
├── test_analysis.py
├── test_api.py
└── fixtures/
    ├── sample_collection.txt
    └── sample_decks.json
```

---

## Git Conventions

### Branch Names

```
feature/<pr-number>-<component>
fix/<pr-number>-<description>
```

### Commit Messages

```
<type>(<scope>): <description>

Types: feat, fix, refactor, test, docs, chore
Scope: models, parser, api, frontend, ml, db
```

### PR Title Format

```
<type>(<scope>): <description>
```

---

## Current State

<!-- Updated after each PR -->

Last PR Merged: #19 frontend-collection
Current PR: #20 frontend-deck-browser
Next PR: #21 frontend-deck-detail
Blockers: None
