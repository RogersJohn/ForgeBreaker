# CLAUDE.md - ForgeBreaker

## Interaction Style

- Be direct and critical. No sycophancy, no "great question!" or "impressive work!"
- Point out flaws, inefficiencies, and problems directly
- If something is mediocre, say so
- Honest technical assessment over politeness

## Project Context

ForgeBreaker is an MTG Arena deck assistant with ML-powered predictions and Claude AI chat. It's the **specialized application** in a 3-repo system:

- **ForgeBreaker** (this repo): All MTG-specific code—training pipeline, 17Lands data, card data, user-facing app
- **MLForge**: Generic ONNX model serving platform (receives trained models from here)
- **MCP-Demo**: Generic REST-to-MCP gateway (registers MLForge as a tool)

ForgeBreaker is the only repo that knows about MTG. The other two are generic infrastructure.

## Critical Rules

1. **TEST-DRIVEN DEVELOPMENT**: Write failing tests first, then implement
2. **SMALL WORK ITEMS**: 1-3 files, <100 lines each, reviewable in Copilot
3. **DO NOT MODIFY RAILWAY CONFIGS**: Never touch `railway.toml`, `railway.json`, `Procfile` unless explicitly approved
4. **NO NETWORK CALLS IN TESTS**: Mock all HTTP requests
5. **AI ASSISTANCE IS ACKNOWLEDGED**: We own that Claude helps write code

## Current Sprint: ML Pipeline (Days 1-4)

### Work Item 1: 17Lands Data Downloader

**Location**: `forgebreaker/ml/data/download_17lands.py`
**Tests**: `tests/ml/test_download_17lands.py`

Download 17Lands public datasets from S3 (no scraping, no rate limits).

**Test cases (write first):**
```python
# URL construction
test_constructs_premier_draft_url  # https://17lands-public.s3.amazonaws.com/analysis_data/game_data/game_data_public.{SET}.{EVENT}.csv.gz
test_set_code_is_uppercased
test_invalid_event_type_raises  # Only: PremierDraft, TradDraft, QuickDraft, Sealed

# File paths
test_generates_path_in_data_directory
test_filename_includes_set_and_event

# Download behavior (mock httpx)
test_downloads_to_correct_path
test_skips_download_if_file_exists
test_raises_on_http_error

# Batch operations
test_downloads_multiple_sets
test_continues_on_single_failure
```

**Implementation requirements:**
- Use `httpx` for HTTP
- Stream large files with `iter_bytes()`
- Custom `DownloadError` exception
- CLI entrypoint: `python -m forgebreaker.ml.data.download_17lands --sets BLB OTJ MKM`

---

### Work Item 2: Data Loading & Schema Validation

**Location**: `forgebreaker/ml/data/loader.py`
**Tests**: `tests/ml/test_loader.py`

**Test cases:**
```python
test_loads_gzipped_csv
test_returns_dataframe
test_validates_required_columns
test_expected_columns_present  # expansion, event_type, draft_id, won, on_play, num_mulligans, user_game_win_rate_bucket, deck_*
test_filters_to_single_set
test_combines_multiple_files
```

**Required columns:**
```python
REQUIRED_COLUMNS = [
    'expansion', 'event_type', 'draft_id', 'game_time',
    'won', 'on_play', 'num_mulligans', 'user_game_win_rate_bucket'
]
# Plus deck_* columns (card counts)
```

---

### Work Item 3: Card Data from Scryfall

**Location**: `forgebreaker/ml/data/card_data.py`
**Tests**: `tests/ml/test_card_data.py`

Fetch card metadata (types, mana values) for feature engineering.

**Test cases:**
```python
test_fetches_set_cards  # Mock Scryfall API
test_caches_card_data  # Don't re-fetch
test_extracts_card_type  # creature, instant, sorcery, etc.
test_extracts_mana_value
test_extracts_colors
test_handles_missing_cards_gracefully
```

**Rate limiting:** Scryfall allows 10 requests/second. Add delays between bulk requests.

---

### Work Item 4: Feature Engineering

**Location**: `forgebreaker/ml/features/engineer.py`
**Tests**: `tests/ml/test_features.py`

**Test cases:**
```python
test_extracts_deck_card_columns
test_counts_total_cards
test_counts_creatures_lands_spells  # Uses card_data
test_calculates_average_mana_value  # Uses card_data
test_extracts_color_pair
test_preserves_game_context_features  # on_play, num_mulligans, user_win_rate
test_creates_target_column  # Binary 'won'
test_output_is_numeric
```

**Feature set:**
```python
FEATURES = [
    # Deck composition
    'n_cards_in_deck', 'n_creatures', 'n_lands', 'n_noncreature_spells',
    'avg_mana_value',
    'curve_1_drop', 'curve_2_drop', 'curve_3_drop', 'curve_4_drop', 'curve_5plus_drop',
    
    # Colors (one-hot)
    'color_W', 'color_U', 'color_B', 'color_R', 'color_G',
    
    # Game context
    'on_play', 'num_mulligans', 'user_skill_bucket',
]
TARGET = 'won'
```

---

### Work Item 5: Model Training

**Location**: `forgebreaker/ml/training/train.py`
**Tests**: `tests/ml/test_training.py`

**Test cases:**
```python
test_splits_data_correctly  # No leakage by draft_id
test_trains_xgboost_model
test_evaluates_on_holdout  # Returns accuracy, AUC
test_exports_to_onnx
test_onnx_produces_same_predictions
test_saves_feature_names
test_generates_model_card
```

**Config:**
```python
MODEL_CONFIG = {
    'n_estimators': 100,
    'max_depth': 6,
    'learning_rate': 0.1,
    'random_state': 42,
}
TRAIN_RATIO, VAL_RATIO, TEST_RATIO = 0.7, 0.15, 0.15
```

**Outputs:**
- `models/deck_winrate_predictor.onnx`
- `models/model_metadata.json`
- `docs/MODEL_CARD.md`

---

### Work Item 6: Upload Model to MLForge

**Location**: `forgebreaker/ml/deploy/upload_model.py`
**Tests**: `tests/ml/test_upload_model.py`

Script to upload trained ONNX model to MLForge API.

**Test cases:**
```python
test_uploads_onnx_file  # Mock MLForge API
test_registers_model_metadata
test_handles_upload_failure
```

---

## File Structure After Sprint

```
forgebreaker/
├── ml/
│   ├── __init__.py
│   ├── data/
│   │   ├── __init__.py
│   │   ├── download_17lands.py
│   │   ├── loader.py
│   │   └── card_data.py
│   ├── features/
│   │   ├── __init__.py
│   │   └── engineer.py
│   ├── training/
│   │   ├── __init__.py
│   │   └── train.py
│   └── deploy/
│       ├── __init__.py
│       └── upload_model.py
├── models/
│   ├── deck_winrate_predictor.onnx
│   └── model_metadata.json
├── data/
│   └── raw/  # Downloaded 17Lands CSVs (gitignored)
└── tests/
    └── ml/
        ├── test_download_17lands.py
        ├── test_loader.py
        ├── test_card_data.py
        ├── test_features.py
        ├── test_training.py
        └── test_upload_model.py
```

---

## Commands

```bash
# Run ML tests
pytest tests/ml/ -v

# Run with coverage
pytest tests/ml/ -v --cov=forgebreaker/ml --cov-report=term-missing

# Download training data
python -m forgebreaker.ml.data.download_17lands --sets BLB OTJ MKM --data-dir data/raw

# Train model
python -m forgebreaker.ml.training.train --data-dir data/raw --output-dir models

# Upload to MLForge
python -m forgebreaker.ml.deploy.upload_model --model models/deck_winrate_predictor.onnx --url $MLFORGE_URL
```

---

## Dependencies to Add

```
# pyproject.toml [project.optional-dependencies] or requirements.txt
pandas>=2.0.0
xgboost>=2.0.0
scikit-learn>=1.3.0
skl2onnx>=1.16.0
onnxruntime>=1.16.0
httpx>=0.25.0
```

---

## PR Workflow

1. Branch: `git checkout -b feat/ml-download-17lands`
2. Tests first: `git commit -m "test: add 17lands downloader tests"`
3. Implementation: `git commit -m "feat: implement 17lands downloader"`
4. Push, PR, Copilot review
5. Merge, next work item

---

## Quality Checks

- [ ] All new tests pass
- [ ] Existing tests still pass
- [ ] No railway config changes
- [ ] Type hints on public functions
- [ ] Docstrings on public functions

---

## AI Assistance

This project is built with Claude as an AI pair programmer. John Rogers provides architecture, direction, and review. Claude assists with implementation. This is explicitly acknowledged—not hidden.
