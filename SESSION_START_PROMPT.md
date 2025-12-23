# ForgeBreaker - Session Start Prompt

Copy this as your first message when starting a new Claude Code session:

---

```
Read SESSION_HANDOFF.md and CLAUDE.md first.

Then tell me:
1. One paragraph: where we left off
2. Current PR status (which PR, review state)
3. Any pending Copilot feedback to address
4. What you recommend we do this session

Don't start coding until I confirm the direction.
```

---

# Workflow Commands

## Starting a New PR

```bash
./scripts/build-next-pr.sh
```

Then follow the prompt to run Claude Code.

## After Claude Finishes Building

```bash
./scripts/check-review.sh
```

This shows Copilot's review status and feedback.

## After Reviewing Feedback

If approved or you're satisfied:
```bash
./scripts/approve-and-continue.sh
```

This merges the PR and advances to the next one.

## End of Session

```bash
./scripts/session-handoff.sh
```

This saves state for the next session.

---

# Typical Session Flow

```
1. Start session
   → Paste session start prompt into Claude Code
   → Claude reads handoff, summarizes state
   → You confirm direction

2. Build PR
   → ./scripts/build-next-pr.sh
   → Claude implements the PR
   → Claude creates draft PR
   → Claude requests Copilot review

3. Wait for review
   → Copilot reviews (usually 1-5 minutes)
   → ./scripts/check-review.sh
   → Review feedback

4. Address feedback (if needed)
   → Claude fixes issues
   → Re-request review

5. Merge and continue
   → ./scripts/approve-and-continue.sh
   → Repeat from step 2

6. End session
   → ./scripts/session-handoff.sh
```

---

# Time Estimate Per PR

| Step | Time |
|------|------|
| Claude builds PR | 5-15 min |
| Copilot reviews | 1-5 min |
| You review feedback | 2-5 min |
| Fix issues (if any) | 5-10 min |
| Merge + advance | 1 min |
| **Total per PR** | **15-35 min** |

With 25 PRs, expect ~10-15 hours total spread across multiple sessions.

---

# Quick Reference

```bash
# See current state
cat .autopilot_state.json

# See what PR you're on
jq '.current_pr' .autopilot_state.json

# Check PR status
gh pr list --state open

# View PR in browser
gh pr view --web

# Skip a PR (emergency only)
jq '.current_pr += 1' .autopilot_state.json > tmp && mv tmp .autopilot_state.json
```
