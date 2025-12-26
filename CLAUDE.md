# CLAUDE.md - ForgeBreaker

## Interaction Style

- Be direct and critical. No sycophancy.
- Point out flaws and inefficiencies directly
- Honest technical assessment over politeness

## Project Context

ForgeBreaker is an MTG Arena deck assistant with ML-powered predictions and Claude AI chat. It's the **specialized application** in a 3-repo system:

- **ForgeBreaker** (this repo): All MTG-specific code—training pipeline, 17Lands data, card data, user-facing app
- **MLForge**: Generic ONNX model serving platform
- **MCP-Demo**: Generic REST-to-MCP gateway

---

## CRITICAL: Work Item Rules

### DO NOT BUILD MONOLITHIC PRs

**STOP. READ THIS BEFORE WRITING ANY CODE.**

Each work item = ONE PR. Do not combine work items.

**Before starting ANY work item, state:**
> "Starting Work Item X. Files: [list]. Proceeding."

**After completing ANY work item, STOP and state:**
> "Work Item X complete. Lint passes. Tests pass. Ready for review."

Then WAIT for approval before continuing.

### LINT BEFORE EVERY COMMIT

```bash
# Run in this exact order, every time:
ruff format .
ruff check . --fix
ruff check .  # Must show zero errors
mypy forgebreaker --ignore-missing-imports
pytest -v

# Only commit if ALL above pass
```

**Do not commit with lint errors. Do not defer fixes.**

### CI MUST PASS

Every commit must pass:
- `ruff format --check .`
- `ruff check .`
- `mypy forgebreaker`
- `pytest --cov=forgebreaker --cov-fail-under=70`

---

## Quality Standards

### API Contracts Required

**Every endpoint MUST have explicit Pydantic models.**

```python
# Bad - implicit contract
@router.post("/predict")
async def predict(data: dict):
    ...

# Good - explicit contract
class DeckPredictionRequest(BaseModel):
    """Request to predict deck win rate."""
    n_creatures: int = Field(..., ge=0, le=40, description="Number of creatures")
    # ... all fields documented

@router.post("/predict", response_model=DeckPredictionResponse)
async def predict(request: DeckPredictionRequest) -> DeckPredictionResponse:
    ...
```

### ML Logic Must Be Documented

**Required: `docs/MODEL_CARD.md`** - See existing file for format.

### Test Coverage Enforced

- Minimum 70% coverage, CI fails below
- Unit tests for all ML logic
- API contract tests for all endpoints

---

## Completed Work

### Phase 1: ML Pipeline
- PR #74-81: 17Lands downloader, loader, Scryfall card data, feature engineering, XGBoost training, ONNX export, MLForge upload
- PR #83: pyproject.toml updates (onnxmltools, xgboost pinning, coverage threshold)

### Phase 2: Quality & Documentation
- PR #84: docs/MODEL_CARD.md
- PR #85: docs/ARCHITECTURE.md
- PR #86: README enhancements (problem statement, examples)
- Work Item 7: API Contract Audit - PASS (all endpoints have explicit Pydantic models)

---

## Documentation

- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** - System design, data flows, module responsibilities
- **[docs/MODEL_CARD.md](docs/MODEL_CARD.md)** - ML model documentation

---

## Commands

```bash
# Lint (run before every commit)
ruff format .
ruff check . --fix
ruff check .
mypy forgebreaker --ignore-missing-imports

# Test with coverage (70% minimum)
pytest -v --cov=forgebreaker --cov-report=term-missing

# Run server
uvicorn forgebreaker.main:app --reload

# View API docs
open http://localhost:8000/docs
```

---

## Quality Checklist (Every PR)

- [ ] ONE work item only
- [ ] `ruff format --check .` passes
- [ ] `ruff check .` passes (zero errors)
- [ ] `mypy forgebreaker` passes
- [ ] `pytest --cov-fail-under=70` passes
- [ ] New endpoints have explicit request/response models
- [ ] New ML logic is documented
- [ ] No railway config changes
- [ ] User approved

---

## Anti-Patterns

- "I'll do work items 1-3 together"
- "I'll fix lint later"
- "The dict works fine, I don't need a Pydantic model"
- "The ML logic is obvious from the code"
- "Tests pass at 45% coverage, that's fine for now"

---

## AI Assistance

Built with Claude as AI pair programmer. John Rogers provides architecture, direction, and code review. This is explicitly acknowledged.
