# Deck Win Rate Predictor

## Model Overview

- **Type**: XGBoost Classifier
- **Task**: Predict probability of winning a draft game based on deck composition
- **Version**: 1.0.0
- **Format**: ONNX (for MLForge deployment)

## Training Data

- **Source**: 17Lands public datasets (https://www.17lands.com/public_datasets)
- **Formats**: Premier Draft, Traditional Draft, Quick Draft, Sealed
- **Size**: Variable (depends on sets downloaded)
- **Splitting**: 70% train, 15% validation, 15% test (split by draft_id to prevent leakage)

## Model Configuration

```json
{
  "n_estimators": 100,
  "max_depth": 6,
  "learning_rate": 0.1,
  "random_state": 42,
  "eval_metric": "logloss",
  "early_stopping_rounds": 10
}
```

## Features

| Feature | Type | Description | Range |
|---------|------|-------------|-------|
| `n_cards_in_deck` | int | Total cards in deck | 35-45 |
| `n_creatures` | int | Number of creature cards | 0-30 |
| `n_lands` | int | Number of land cards | 10-20 |
| `n_noncreature_spells` | int | Number of non-creature, non-land cards | 0-20 |
| `avg_mana_value` | float | Average mana value of non-land cards | 1.0-5.0 |
| `curve_1_drop` | int | Cards with mana value 1 | 0-10 |
| `curve_2_drop` | int | Cards with mana value 2 | 0-15 |
| `curve_3_drop` | int | Cards with mana value 3 | 0-10 |
| `curve_4_drop` | int | Cards with mana value 4 | 0-8 |
| `curve_5plus_drop` | int | Cards with mana value 5+ | 0-6 |
| `color_W` | binary | Deck contains white cards | 0 or 1 |
| `color_U` | binary | Deck contains blue cards | 0 or 1 |
| `color_B` | binary | Deck contains black cards | 0 or 1 |
| `color_R` | binary | Deck contains red cards | 0 or 1 |
| `color_G` | binary | Deck contains green cards | 0 or 1 |
| `on_play` | binary | Player is on the play | 0 or 1 |
| `num_mulligans` | int | Number of mulligans taken | 0-6 |
| `user_skill_bucket` | float | Player's historical win rate bucket | 0.0-1.0 |

## Output

- **`win_probability`**: float between 0 and 1
  - Represents the predicted probability of winning the game
  - Threshold of 0.5 for binary win/loss classification

## Performance Metrics

Performance varies by set and format. Typical metrics on holdout test set:

- **Accuracy**: ~55-60% (baseline random: 50%)
- **AUC-ROC**: ~0.55-0.62

Note: Draft games have inherent variance. A well-calibrated model predicting slightly better than random is expected given the feature set focuses on deck composition, not individual card power levels.

## Limitations

1. **Deck composition only**: Does not account for individual card power levels or synergies
2. **No opponent modeling**: Predictions don't consider opponent's deck or skill
3. **Set-specific performance**: Model trained on specific sets may not generalize well to new sets
4. **Skill bucket dependency**: Predictions are heavily influenced by the player's historical win rate
5. **Limited format coverage**: Trained on limited (draft/sealed) formats, not constructed

## Failure Modes

| Scenario | Behavior |
|----------|----------|
| Missing required feature | Returns 400 Bad Request with validation error |
| Feature value out of expected range | Model still produces prediction (may be less reliable) |
| New set with different mechanics | May produce unreliable predictions |
| Extreme deck compositions | Predictions may be overconfident |

## Ethical Considerations

- Model predictions should be used as suggestions, not guarantees
- Players should not rely solely on model output for deck building decisions
- Win rate predictions may discourage experimentation with unconventional decks

## Usage

### Input Format (ONNX)

Features must be provided as a float32 array with 18 elements in the order listed above.
Feature names are mapped to `f0`, `f1`, ..., `f17` in the ONNX model.

### Example Request to MLForge

```json
{
  "features": {
    "n_cards_in_deck": 40,
    "n_creatures": 15,
    "n_lands": 17,
    "n_noncreature_spells": 8,
    "avg_mana_value": 2.8,
    "curve_1_drop": 3,
    "curve_2_drop": 6,
    "curve_3_drop": 5,
    "curve_4_drop": 3,
    "curve_5plus_drop": 2,
    "color_W": 1,
    "color_U": 1,
    "color_B": 0,
    "color_R": 0,
    "color_G": 0,
    "on_play": 1,
    "num_mulligans": 0,
    "user_skill_bucket": 0.55
  }
}
```

### Example Response

```json
{
  "win_probability": 0.58,
  "model_version": "1.0.0"
}
```

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2025-12-26 | Initial release with XGBoost classifier |
