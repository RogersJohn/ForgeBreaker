# ForgeBreaker

## Why does my deck feel inconsistent?

That's the question ForgeBreaker helps you answer.

Not "what's the best deck" or "what's my winrate." Those tools exist. ForgeBreaker asks different questions:

- **"Which card is my deck secretly relying on?"**
- **"What happens when this assumption fails?"**
- **"What part of my deck breaks first?"**

If you've ever lost a game and thought "that felt unlucky, but was it?" — ForgeBreaker helps you find out.

---

## What ForgeBreaker Actually Does

ForgeBreaker makes your deck's **assumptions** visible.

Every deck relies on assumptions you may not have articulated:

- "I'll hit my third land drop by turn 3"
- "Monastery Swiftspear will connect at least twice"
- "I'll draw removal before their threat lands"

These aren't guarantees. They're assumptions. And when they fail, your deck underperforms.

**ForgeBreaker surfaces these assumptions, lets you stress them, and shows you what breaks.**

### The Core Loop

```
1. Surface Assumptions
   → See what your deck depends on (mana curve, key cards, interaction timing)

2. Stress Test
   → Ask "what if this card underperforms?" or "what if I'm a turn behind?"

3. Find the Breaking Point
   → Discover which assumption failing hurts you most

4. Understand Why
   → Every result explains what changed and what it depends on
```

---

## What ForgeBreaker Does NOT Do

**ForgeBreaker does not track your ladder performance.**

It doesn't know your rank. It doesn't log your matches. It cannot tell you "play this deck to climb."

**ForgeBreaker does not predict winrates.**

Meta winrate data is displayed for context, sourced from public aggregators. But ForgeBreaker does not claim to predict *your* winrate. Your results depend on your skill, your meta pocket, and variance.

**ForgeBreaker does not optimize for meta dominance.**

It won't tell you "Deck X is 2% better than Deck Y." It helps you understand *why* a deck works, not *whether* it's statistically optimal.

**ForgeBreaker is not a replacement for playtesting.**

Understanding that your deck relies on resolving a turn-2 threat doesn't mean you've played the games. It means you know what to watch for when you do.

---

## Who This Is For

**Deck brewers** who want to understand why their creations succeed or fail.

**Budget-conscious players** who need to know if spending wildcards on Deck X will actually address the consistency problems they're experiencing with Deck Y.

**Theorycrafters** who want to articulate and test the assumptions behind their deck choices.

**Players who ask "why"** instead of just "what."

---

## Key Concepts

### Assumptions

An **assumption** is something your deck needs to be true to function as designed.

Examples:
- "I have at least 8 one-drops for consistent turn-1 plays"
- "My removal will answer their early threats before I stabilize"
- "I'll draw one of my 4 payoff cards in the first 10 cards"

ForgeBreaker identifies these assumptions from your decklist and card database.

### Fragility

**Fragility** measures how sensitive your deck is to assumption failures.

A fragile deck breaks when one thing goes wrong. A resilient deck can absorb variance.

ForgeBreaker calculates fragility by checking how many assumptions are outside healthy ranges and how severely.

### Breaking Point

The **breaking point** is the assumption that, when stressed, causes the largest increase in fragility.

Finding your breaking point tells you where to focus if you want to improve consistency.

### Stress Testing

**Stress testing** means intentionally worsening an assumption to see the impact.

- "What if my key card is answered every time?"
- "What if I miss my third land drop?"
- "What if the meta has more removal than expected?"

ForgeBreaker simulates these scenarios and shows you the before/after fragility change.

---

## How It Works

1. **Import your collection** — Paste your Arena export
2. **Browse meta decks** — See competitive lists with completion percentages
3. **Select a deck** — View its assumptions, fragility, and key dependencies
4. **Stress test** — Ask "what if?" and see what breaks
5. **Understand the result** — Every outcome includes an explanation

---

## Technical Details

### Tech Stack

- **Backend**: Python 3.11+ / FastAPI
- **Frontend**: React 19 / TypeScript / Tailwind CSS
- **Database**: PostgreSQL (async via SQLAlchemy 2.0)
- **LLM**: Claude API with MCP tool calling

### Development Setup

```bash
# Backend
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
export DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/forgebreaker"
uvicorn forgebreaker.main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `ANTHROPIC_API_KEY` | Claude API key (for chat) |

---

## License

MIT
