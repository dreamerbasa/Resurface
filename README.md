# Dropzone

AI-powered personal knowledge aggregator that captures scattered saves from Instagram, LinkedIn, Substack, and voice notes — auto-classifies them and resurfaces what matters.

## The Problem

I save things across 5 platforms. None of it connects. All of it gets forgotten. The problem isn't capture — it's that saved ≠ remembered.

## How It Works

Share anything to a Telegram bot. It auto-detects the format, extracts the content, classifies it into user-defined categories using AI, and stores it structured.

**Supported inputs:**
- **Text** — raw ideas, thoughts, notes
- **URLs** — articles from Substack, LinkedIn, Medium, YouTube (with transcript extraction), and any web page
- **Screenshots** — Instagram posts, infographics, job listings (vision API reads the content, filters out UI noise)
- **Voice notes** — transcribed via Whisper, then classified like text

After saving, the bot prompts for two quick ratings: interest level and goal alignment. These feed the upcoming resurfacing engine.

## Architecture

Two-step pipeline: **extract** then **classify**.

```
Input → Format Detector → Extractor → Classifier → Supabase → Nudge Engine (coming soon)
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

## What's Next

- Resurfacing engine with 3x3 priority matrix (interest x goal alignment)
- Daily nudges + weekly themed digests
- Cross-source clustering (connecting a Substack article with an Instagram save about the same topic)

## Tech Stack

Python, Telegram Bot API, OpenAI (GPT-4o-mini + Whisper), Supabase (Postgres + pgvector), trafilatura, youtube-transcript-api, python-telegram-bot

## Status

Milestone 2 of 5 complete. Actively building in public.
