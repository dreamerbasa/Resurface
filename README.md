# Cue

Save. Remember. Learn.

Personal AI tool that captures saves from multiple platforms, classifies them, and resurfaces what matters through lifecycle-based nudges and semantic clustering.

[Live site](https://dreamerbasa.github.io/Cue/) · [Demo video](https://youtube.com/watch?v=nmrZKs7fYko)

## Architecture

**System overview:**

```
Telegram Bot → Python Backend
        │
┌───────────┼───────────┐
│           │           │
Vision API   trafilatura   Whisper
(images)     (URLs)        (voice)
│           │           │
└───────────┼───────────┘
            │
      LLM Classifier
            │
    Supabase (pgvector)
            │
┌──────────┼──────────┐
│          │          │
Daily Nudge  Weekly     Nightly
(Telegram)   Digest     Reminder
             (Email)    (Telegram)
```

**Pipeline detail:**

```
Input → Format Detector → Extractor → Classifier → Supabase → Nudge Engine
              │                │             │
              │          ┌─────┴─────┐       └── LLM assigns category,
              │          │ text      │           title, summary, tags
              │          │ url       │
              │          │ vision    │
              │          │ whisper   │
              │          └───────────┘
              └── URL? Voice? Screenshot? Plain text?
```

**Key design decisions:**
- **Format-specific extraction, format-agnostic classification** — each input type has its own extractor, but all feed the same classifier. Adding a new format means writing one extractor, not touching classification logic.
- **Dynamic categories from database, not hardcoded** — categories live in Supabase and are fetched at classification time. Users can add or rename categories without code changes.
- **Stateless rating system** — ratings work hours after saving. No in-memory state; every button tap queries and updates the database directly, surviving bot restarts.

## The Resurfacing Engine

The first version used a single scoring formula: `(interest * 3) + (goal * 2) + age_penalty + unseen_bonus`. It broke — old high-interest items permanently outranked new ones, and there was no way to tune one behavior without breaking another.

The redesign uses lifecycle phases with explicit rules:

**Phase 1 — First Look.** Every item gets surfaced at least once within 7 days, regardless of score. Higher-priority items surface sooner (day 1-2 vs day 5-6). This guarantees nothing is forgotten.

**Phase 2 — Priority Rotation.** After first look, items enter a cooldown-based rotation. The 3×3 priority matrix (interest × goal alignment) determines frequency. High/high items resurface every 2-3 days. Low/low items every 7+ days.

**Phase 3 — Decay.** Items surfaced 3+ times without action trigger escalation — a keep-or-drop decision forced on the user. This prevents infinite accumulation.

**Exceptions:**
- Goal-aligned items (goal = 3) never decay, regardless of times surfaced
- "Remind tonight" items bypass the lifecycle and surface in the nightly reminder
- Weekend mode: users with email set get the digest instead of nudges; users without email get normal nudges + a Saturday prompt to set up email

## Clustering

HDBSCAN over DBSCAN because DBSCAN requires a fixed `eps` (neighborhood radius) that breaks when the embedding distribution shifts as the dataset grows. HDBSCAN adapts automatically — it finds clusters of varying density without manual tuning.

**Embedding composition:** `title + " — " + summary` fed to `text-embedding-3-small`. Title alone clusters too aggressively on keywords. Adding tags added noise. Title + summary hits the signal sweet spot.

**Theme generation:** After clusters form, the titles within each cluster are passed to GPT-4o-mini to generate a human-readable theme name and emoji. No predefined taxonomy.

**Usage:** The weekly Saturday digest groups items into themed clusters, connecting saves from different platforms (an Instagram screenshot, a Substack article, and a voice note about the same topic appear together).

## What I Learned

- A scoring formula that sums everything into one number is fragile — lifecycle phases with explicit rules are more predictable and debuggable
- DBSCAN needs a fixed eps that breaks when data changes — HDBSCAN adapts automatically
- Two features (Remind Tonight, Go Deep) came from actually using the product daily, not from planning
- Embedding title + summary produces better clustering signal than title alone or title + tags

## Tech Stack

Python · Telegram Bot API · OpenAI (GPT-4o-mini + Whisper + Embeddings) · Supabase (Postgres + pgvector) · HDBSCAN · SendGrid · Railway

## Project Docs

- [Architecture doc](docs/architecture.md)
- [Build journal](docs/build-journal.md)
