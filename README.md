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

## Usage Limits & Cost Controls

ForgeBreaker is a **demo/portfolio project**. To prevent abuse and control LLM costs, the following limits are enforced:

### Per-User Rate Limits

| Limit | Default | Description |
|-------|---------|-------------|
| Requests per IP per day | 20 | Each IP address gets 20 chat requests per day |

When you exceed the rate limit, you'll receive an HTTP 429 response with a friendly message explaining the limit resets at midnight UTC.

### Global Daily Budgets

| Limit | Default | Description |
|-------|---------|-------------|
| LLM calls per day | 500 | Total Claude API calls across all users |
| Tokens per day | 500,000 | Total tokens (input + output) across all users |

These are **hard caps**. When exceeded, the service returns HTTP 503 until the next day.

### Emergency Kill Switch

The `LLM_ENABLED` environment variable can be set to `false` to immediately disable all LLM functionality without redeploying. This is useful for:
- Cost emergencies
- Maintenance windows
- API key rotation

### Monitoring

The `/diagnostics/usage-stats` endpoint shows current usage:
- Unique IPs today
- LLM calls made / remaining
- Tokens used / remaining
- Current limits

### Why These Limits Exist

1. **Cost control**: Claude API calls cost money. These limits prevent unexpected bills.
2. **Fair access**: Per-IP limits ensure one user can't monopolize the service.
3. **Demo appropriate**: This is a portfolio project, not a production service.

If you're interested in running ForgeBreaker without limits, you can self-host with your own API key.

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
| `LLM_ENABLED` | Kill switch for LLM (default: `true`) |
| `REQUESTS_PER_IP_PER_DAY` | Per-IP rate limit (default: `20`) |
| `MAX_LLM_CALLS_PER_DAY` | Global daily LLM call limit (default: `500`) |
| `MAX_TOKENS_PER_DAY` | Global daily token limit (default: `500000`) |

---

## Security Model

ForgeBreaker is a **portfolio demonstration project**, not a production service.

**What this project demonstrates:**
- Clean API architecture with FastAPI
- Domain modeling for a complex problem space
- Test-driven development with high coverage
- LLM integration via Claude API

**What this project does NOT implement:**
- Authentication or authorization
- Secure user identity (browser UUIDs are used for session continuity, not security)
- Data privacy guarantees
- Multi-tenant isolation

**CORS is intentionally open.** The API accepts requests from any origin. This is appropriate for a demo project where the goal is showcasing architecture, not protecting user data.

**User identifiers are browser-generated UUIDs.** They provide session continuity across page reloads, nothing more. Anyone with the UUID can access that "user's" data. This is acceptable because the only data stored is card collection lists with no real-world value.

If you're evaluating this project for an interview: the security decisions here are intentional and appropriate for the demo context. Production deployment would require authentication, proper CORS configuration, and rate limiting—none of which are the focus of this demonstration.

---

## License

MIT
