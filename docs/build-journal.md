# Resurface — Build Journal & Learning Log

## What is this project?

A personal knowledge aggregator. You save stuff across Instagram, LinkedIn, Substack, voice notes, and random text thoughts — all scattered, all forgotten. Resurface funnels everything into one Telegram bot, auto-classifies it using AI, stores it structured in a database, and (eventually) nudges you to revisit what matters.

---

## What's been built so far

### Milestone 1: Capture Pipeline MVP ✅

**What it does:** You send a text message to the Telegram bot → an LLM classifies it into a category, generates a title, summary, and tags → it's stored in Supabase → bot replies confirming what was saved.

**What you built/did:**
- Created the Supabase project, configured security settings (Data API on, auto-expose off, RLS on)
- Created the GitHub repo, set up project board with milestones and issues
- Made the decision to use Gemini free tier over Claude API ($20 minimum) for cost reasons
- Decided on the project name
- Ran all tests, debugged the RLS permission issue
- Used the bot from your phone to verify end-to-end

**What Claude Code wrote:**
- `config.py` — loads environment variables, initializes API clients
- `db/queries.py` — get_categories() and insert_item() functions
- `pipeline/extractors/text.py` — passthrough extractor for plain text
- `pipeline/classifier.py` — sends text + category list to LLM, parses JSON response
- `pipeline/router.py` — orchestrates extract → classify → store
- `bot/capture_bot.py` — Telegram bot handler for text messages
- `main.py` — entry point
- `test_pipeline.py` — test script with hardcoded messages

### Milestone 2: Multi-format Capture + Ratings ✅

**What it does:** You can now send the bot screenshots, URLs, voice notes, and text — all get classified, stored, and rated. This covers your entire real-world capture flow.

**What you built/did:**
- Ran DB migration (ALTER TABLE) in Supabase, updated schema.sql with logical column ordering
- Created Supabase Storage bucket for temporary screenshot storage
- Tested every extractor individually from command line before wiring to bot
- Debugged Instagram oEmbed failure (Meta blocks it), decided on screenshot fallback
- Debugged Medium extraction failure, created P3 issue for future fix
- Debugged YouTube transcript API syntax change (old docs vs new API)
- Tested full URL suite: Substack, YouTube with captions, YouTube Shorts, Instagram, Medium, random blogs, URLs in messages, dead URLs
- End-to-end tested from Telegram: screenshots, URLs, voice notes, mixed content
- Tested edge cases: multiple photos in album, multiple URLs in one message, rapid fire messages, image with caption
- Made all architecture and fallback decisions

**What Claude Code wrote:**
- `pipeline/extractors/vision.py` — GPT-4o-mini Vision with UI noise filtering prompt, Supabase Storage upload, base64 encoding, caption-as-user-note
- `pipeline/extractors/url.py` — domain detection sub-router, trafilatura with browser headers, YouTube transcript + oEmbed, Instagram/Medium screenshot fallback, multiple URL handling, user note extraction
- `pipeline/extractors/whisper.py` — Whisper API transcription, temp file cleanup
- Updated `pipeline/router.py` — content type routing for all 4 types, URL detection in text, needs_screenshot handling, multiple URL support
- Updated `bot/capture_bot.py` — photo handler, voice handler, URL detection in text handler, rating inline keyboards, callback handlers, caption handling
- `db/queries.py` — update_item_rating() function

**Key issues found and resolved:**

| Issue | Root cause | Fix |
|---|---|---|
| Instagram oEmbed returns HTML instead of JSON | Meta restricted the endpoint, requires auth now | Skip all fetching, return needs_screenshot |
| Medium extraction returns empty | JS-heavy page, trafilatura can't render | Screenshot fallback, P3 issue created |
| YouTube transcript AttributeError | Library updated API from class method to instance method | Changed to YouTubeTranscriptApi().fetch() |
| trafilatura returns YouTube footer only | YouTube is JS-rendered, static HTML is just boilerplate | Added YouTube-specific handling, skip trafilatura for youtube.com |
| Multiple URLs in one message only processing first | extract() was finding single URL only | Added extract_multiple() and loop in router |

---

## Key concepts you should understand

### The two-step pipeline

This is the core architectural decision. Every piece of content goes through:

**Step 1 — Extract:** Convert the raw format into plain text. Image → OCR text. URL → article text. Voice → transcription. Text → passthrough. Each extractor is format-specific but dumb — no intelligence, no classification.

**Step 2 — Classify:** Take the plain text (regardless of where it came from) and send it to an LLM with the prompt "here are my categories, classify this." One prompt, one function, works the same for all content types.

**Why this matters:** If you combined extraction and classification into one step per content type, you'd have 4 different classifier prompts to maintain. By separating them, the classifier doesn't know or care if the text came from a screenshot or a voice note. One place to tune classification = one place things can break.

### How the Telegram bot works

The `python-telegram-bot` library gives you handler functions. You register them once:
- `filters.PHOTO` → fires when an image arrives
- `filters.VOICE` → fires for voice notes
- `filters.TEXT` → fires for plain text

Telegram detects the content type, your handler receives it. No custom detection logic needed.

The bot runs in "polling" mode — it periodically asks Telegram's servers "any new messages for me?" This is simpler than webhook mode (where Telegram pushes messages to your server) and works without a public URL.

### How Supabase works in this project

Supabase is a managed Postgres database with extras. You interact with it through the `supabase-py` Python library, which sends HTTP requests to Supabase's REST API.

Two tables:
- `categories` — your classification taxonomy. The LLM reads these to know what buckets exist.
- `items` — every piece of content you save. Raw input + processed output + resurfacing state.

The key insight: categories are stored in the database, not hardcoded. So when the classifier runs, it fetches the current category list from Supabase. If you add a new category via bot command, the classifier automatically starts using it. No code change, no redeployment.

**API keys:**
- `service_role` (legacy tab, starts with `eyJ...`) — bypasses Row Level Security, full access. Used by your backend.
- `anon` / publishable — respects RLS, meant for client-side. Not used in this project.
- The new "publishable" and "secret" keys on the main tab are Supabase's updated key format, but the Python library works better with the legacy JWT keys.

### How the LLM classifier works

The classifier builds a prompt that includes:
1. A system instruction: "You are a content classifier. Return JSON only."
2. The full list of categories with descriptions (fetched from Supabase)
3. The extracted text to classify

The LLM returns JSON like:
```json
{
    "category_name": "business_idea",
    "title": "Survivorship-bias-free data for quant funds",
    "summary": "An idea for providing clean historical data...",
    "tags": ["quant", "data", "fintech"]
}
```

The code parses this JSON, looks up the category UUID by matching the name, and stores everything in the items table.

**Dynamic categories** are the key design choice. The classifier prompt is rebuilt every time with whatever categories exist in the DB. Add a category → classifier uses it next time. No code change needed.

### URL extraction strategies

Different websites need different approaches:

**trafilatura** — a Python library built for extracting article content from web pages. Give it a URL, it returns clean text with nav/ads/footers stripped. Works on most blogs, news sites, Substack. Uses `favor_recall=True` to be less strict about what counts as "content."

**YouTube oEmbed** — YouTube provides a free API endpoint (`youtube.com/oembed?url=...&format=json`) that returns the video title and author. No auth needed.

**youtube-transcript-api** — pulls the auto-generated captions from YouTube videos. Not the audio — the text subtitles YouTube already has. Free, fast, no API key. Newer versions use `YouTubeTranscriptApi().fetch(video_id)` syntax (not the old `get_transcript` class method).

**Instagram/Medium** — both block all scraping. Instagram redirects to login, Medium returns empty content. Handled by asking the user to send a screenshot instead.

### The router pattern

`pipeline/router.py` is the orchestrator. It:
1. Detects content type (text with URL? plain text? image? voice?)
2. Calls the right extractor
3. Checks for special cases (needs_screenshot → skip classification)
4. Calls the classifier
5. Merges extractor output + classifier output
6. Inserts into database
7. Returns the result for the bot to display

The bot only calls `process_message()`. It doesn't know about extractors, classifiers, or database queries. This separation means adding a new content type only requires changes in the router and a new extractor — the bot code stays the same.

---

## Problems encountered and how they were solved

### RLS permission denied error
**Problem:** test_pipeline.py returned "permission denied for table categories" for all 3 tests.
**Root cause:** Used the new "publishable" API key (from the main tab) which respects RLS. Tables had RLS enabled with no policies allowing access.
**Fix:** Switched to the legacy `service_role` key (starts with `eyJ...`) which bypasses RLS entirely. The Python library works better with legacy JWT keys.
**Lesson:** Supabase has two key systems (new and legacy). For server-side Python backends, use legacy service_role.

### Instagram oEmbed not working
**Problem:** Instagram oEmbed API returns an HTML login page instead of JSON, even though status code is 200.
**Root cause:** Meta restricted the oEmbed endpoint — it now requires authentication/cookies.
**Fix:** Skip all fetching for Instagram URLs. Return `needs_screenshot: True` and let the user send a screenshot instead. The Vision API path gives better extraction anyway (reads the full image, text overlays, recipe cards).
**Lesson:** Don't fight platforms that actively block scrapers. Find a better path.

### Medium extraction failing
**Problem:** trafilatura returns None for Medium articles, even with browser User-Agent and Google referer headers.
**Root cause:** Medium's JavaScript-heavy rendering doesn't give trafilatura enough static HTML to work with.
**Fix:** Same as Instagram — screenshot fallback. Marked as P3 enhancement (Issue 25) to explore headless browser or RSS feed approaches later.

### YouTube transcript API syntax change
**Problem:** `YouTubeTranscriptApi.get_transcript()` throws AttributeError.
**Root cause:** Library updated its API. Class method changed to instance method.
**Fix:** Changed to `YouTubeTranscriptApi().fetch(video_id)` — the current syntax.
**Lesson:** AI code assistants use training data that may be outdated. When a library call fails with AttributeError, the API likely changed — check the library's current docs/version.

### trafilatura returning YouTube footer only
**Problem:** YouTube pages return just "About Press Copyright Contact us..." instead of video content.
**Root cause:** YouTube pages are JS-rendered. trafilatura only sees the static HTML shell.
**Fix:** Added YouTube-specific handling: use youtube-transcript-api for captions + oEmbed for title, skip trafilatura entirely for youtube.com domains.

### Git author identity error
**Problem:** `git commit` failed with "Author identity unknown."
**Fix:** Set global git config with email (same as GitHub account) and name.

### Windows vs Linux/Mac commands
**Problem:** `mkdir -p` and `touch` commands failed in PowerShell.
**Fix:** Used Windows equivalents: `mkdir folder1, folder2` and `New-Item file1, file2`.

### python-telegram-bot JobQueue missing
**Problem:** Railway deploy crashed with `AttributeError: 'NoneType' object has no attribute 'run_repeating'` when trying to use JobQueue for scheduled tasks.
**Root cause:** `python-telegram-bot` base package doesn't include APScheduler. JobQueue is an optional extra. Locally it worked because APScheduler was already installed from earlier experimentation. Railway installs fresh from requirements.txt — base package only.
**Fix:** Changed `python-telegram-bot==21.6` to `python-telegram-bot[job-queue]==21.6` in requirements.txt. The `[job-queue]` syntax installs the optional APScheduler dependency.
**Lesson:** Local "it works" doesn't mean production "it works." Railway starts fresh. Optional extras must be explicit in requirements.txt.

### Nudge scheduling and timezone bugs (found during Milestone 3 testing)
Several bugs surfaced while building and testing the daily nudge and nightly reminder:
- **30-min window matching returned same start/end** (16:00-16:00 instead of 16:00-16:29) — window_end wasn't adding 29 minutes.
- **Job ran from deploy time, not clock-aligned** — fixed by calculating delay until next :00/:30 boundary and using it as first_run.
- **Timezone overflow** (`hour must be in 0..23`) — manual hour addition for IST conversion overflowed. Fixed with proper `timezone(timedelta(hours=5, minutes=30))`.
- **Markdown parse error** (`can't find end of entity`) — special characters in titles broke Telegram's Markdown parser. Switched to HTML parse mode with escaping.
- **Callback handler conflict** — the rating handler caught nudge button clicks and tried to parse UUIDs as integers. Fixed with pattern filters on each CallbackQueryHandler.
- **Nightly reminder never fired** — Postgres TIME returns "22:00:00" but comparison used "22:00". Fixed by stripping seconds.
- **URL preview card cluttered nudge** — added `disable_web_page_preview=True`.

## Known deferred issues (from QC review, not yet fixed)

A comprehensive code QC was run at the end of Milestone 3. Seven issues were fixed (2 critical, 5 medium-that-matter). The following were consciously deferred with reasoning:

**By design, not bugs:**
- Escalation items (surfaced 3+ times) have no cooldown — intentional, high-priority items should push aggressively.
- Rating interest=2 (medium) treated as "not changed" because 2 is the DB default — acceptable tradeoff.

**Already handled gracefully:**
- Nudge sessions lost on bot restart — shows "expired" message, doesn't crash. Persisting to DB is future polish.
- callback_data length — currently safe (50 of 64 bytes used).

**Low priority / premature optimization at current scale:**
- get_categories() called on every classify — could cache with TTL. Negligible at 7 saves/day.
- _get_user_id makes 2 DB calls per message — could combine into one upsert.
- scoring fetches all items with full text — could optimize column selection for power users.
- last_active_at not updated on rating/nudge button taps — cosmetic.
- OpenAI client created at import even if only using Gemini — fails clearly at call time if misconfigured.
- callback_data tampering (forged item IDs) — low risk for single-user bot with AUTHORIZED_USER_IDS. Would need per-item ownership check for multi-user scale.
- Unknown LLM_PROVIDER value would crash — env var is controlled, low risk. Guard can be added later.

These are logged for revisit if the project scales to multiple active users or a power user with hundreds of items.

---

## Decisions made and why

| Decision | Choice | Why |
|---|---|---|
| Capture channel | Telegram bot | Free API, share-sheet works on Android, multi-content support, zero UI to build |
| Two bots vs one bot | Single bot (Dropzone) | Low volume (~7 saves/day) doesn't create clutter. Shareability: explaining 2 bots is friction. Review need is solved by /review command + pinned message, not a separate chat. |
| Sync vs async pipeline | Synchronous | ~5 sec wait is fine for 2 items/day. No queue/worker complexity. |
| LLM provider | OpenAI (started Gemini, switched) | Already had $3 credits. Gemini free tier was first choice for zero cost. |
| Database | Supabase (Postgres + pgvector) | Free tier, managed, vector search built in, Python SDK |
| Categories in DB vs hardcoded | Database | Classifier prompt rebuilds dynamically. Add category → works immediately. |
| Instagram handling | Screenshot fallback | Instagram blocks all scraping. Vision API reads screenshots better anyway. |
| Medium handling | Screenshot fallback (P3 to improve) | Blocked. Low priority — small portion of saves. |
| YouTube extraction | Transcript API + oEmbed fallback | Captions give full content for free. Title-only fallback for videos without captions. |
| Separate extract and classify steps | Two-step pipeline | One classifier prompt regardless of content type. One place to tune. |
| Column order mismatch (live DB vs schema.sql) | Accept it | Postgres doesn't care about column order. schema.sql has logical grouping, live DB has ALTER-appended order. Both work. |
| Project tracking | GitHub Issues + Project Board | Lives with code. Visible to portfolio reviewers. Industry standard. |
| Chat ID storage | Auto-capture in users table via /start | No manual CHAT_ID in .env. Scales to multiple users automatically. |
| Multi-user support | Users table + AUTHORIZED_USER_IDS | Users table stores chat_id, preferences, activity. AUTHORIZED_USER_IDS controls access. Adding a friend = add their ID + they send /start. |
| Nudge persistence | Repeat until acted on, escalate after 3 ignores | Items don't disappear when ignored. After 3 surfaces, forces "keep or drop" decision. |
| Reminder/nudge times | Per-user in DB, configurable via /remindertime and /nudgetime | Not a global config. Each user sets their own schedule. |
| Hosting | Railway | Auto-deploys from GitHub. Free tier covers lightweight polling bot. |

---

## Current project state

**Milestone 1: Capture Pipeline MVP** ✅
**Milestone 2: Multi-format Capture + Ratings** ✅
**Milestone 3: Smart Resurfacing + Nudges** — in progress

**Working — full capture pipeline:**
- Dropzone bot receives text, images, URLs, and voice notes
- Text → passthrough → classify → store ✅
- Images → GPT-4o-mini Vision (UI noise filtered) → classify → store ✅
- URLs → trafilatura/YouTube transcript/screenshot fallback → classify → store ✅
- Voice → Whisper transcription → classify → store ✅
- Instagram/Medium URLs → screenshot redirect ✅
- Multiple photos in album → each processed separately ✅
- Multiple URLs in one message → each extracted and classified separately ✅
- Image with caption → caption stored as user note ✅
- URL with surrounding text → text stored as user note ✅
- Rating buttons (interest + goal alignment) after each save ✅
- Ratings work even hours after saving (stateless, DB-backed) ✅
- Items appear in Supabase with correct categories, titles, summaries, tags
- Access control — bot restricted to authorized users ✅
- Deployed on Railway — bot runs 24/7 ✅
- Bot renamed to Dropzone ✅

**Milestone 3 progress:**
- Users table created with auto chat_id capture ✅
- Multi-user item ownership (user_id on items) ✅
- /start command with full onboarding message (first-time vs returning user) ✅
- /stop command — pauses nudges ✅
- /remindertime, /nudgetime commands ✅
- Nightly capture reminder — deployed on Railway ✅
- JobQueue fix (python-telegram-bot[job-queue] extra) ✅
- Scoring algorithm — lifecycle phases with weekend catch-up ✅
- Daily nudge with action buttons and escalation ✅
- /review command — on-demand pending items queue ✅
- QC pass — 7 bugs fixed (2 critical, 5 medium) ✅
- Logging cleanup — proper Python logging with levels ✅
- Pinned review queue — designed, built, then dropped (nudge + /review covers the need)
- Embeddings generation — deferred to Milestone 4

**Features discovered from real usage (2 days of using the product):**
- "Remind tonight" — save an article now, get reminded in the nightly check-in. Flags item for nightly reminder, no new scheduler. (Issue 29, Milestone 4)
- "Go deep" — flag an article for a detailed learning roadmap in the weekly digest. LLM generates key concepts, learning path, related topics. (Issue 30, Milestone 4)

Both features came from actually using the bot daily, not from planning. This validates the "build vertical, use it, then widen" approach.

**Not yet built:**
- "Go deep" learning roadmaps in weekly digest — Milestone 4 (Issue 30)
- Clustering logic (DBSCAN) — Milestone 4 (Issue 17)
- Weekly email digest — Milestone 4 (Issue 18)
- Semantic search upgrade — Milestone 4 (Issue 31)
- Image cleanup job — Milestone 4 (Issue 20)
- Cost tracking — Milestone 5 (Issues 21-23)
- Instagram reel transcription — Milestone 5 (Issue 24)
- Medium article extraction improvement — Milestone 5 (Issue 25)

**Completed in Milestone 4:**
- "Remind tonight" at save time ✅ (Issue 29)
- Embeddings generation — OpenAI text-embedding-3-small, async post-save ✅ (Issue 16)
- Bot commands — /categories, /search (keyword), /stats ✅ (Issue 19)
- Backfill script for existing items ✅
- HDBSCAN clustering — no eps tuning, adapts to data ✅ (Issue 17)
- Weekly email digest via SendGrid — Saturday full + Sunday follow-up ✅ (Issue 18)
- "Go deep" button — category-aware deep dives in digest ✅ (Issue 30)
- Sunday nightly reminder with cleanup action buttons ✅
- Professional HTML email template ✅
- Rating buttons persist independently ✅
- Nightly reminder "remind tonight" items are actionable ✅

**Key design decisions in Milestone 4:**
- Embeddings via OpenAI API over local sentence-transformers — no Railway RAM increase, negligible cost
- Embedding generated AFTER bot acknowledgment (async) — no response time impact
- HDBSCAN over DBSCAN — fixed eps was too strict, HDBSCAN finds its own thresholds
- "Go deep" is category-aware, not a fixed roadmap template
- Digest = email (read-only) + Telegram cleanup (actionable). No FastAPI web endpoints needed.
- Digest sends at user's nudge_time. Saturday = full, Sunday = follow-up, weekdays = nudge.
- Removed stats and standalones from digest — commands cover these.

**Not yet built (Milestone 5):**
- Semantic search upgrade (Issue 31)
- Image cleanup job (Issue 20)
- Cost tracking (Issues 21-23)
- Instagram reel transcription (Issue 24)
- Medium article extraction (Issue 25)
- Embedding quality optimization (Issue 32)

**Things to study / understand deeper:**
- HDBSCAN — hierarchical density-based clustering, min_cluster_size, difference from DBSCAN/k-means
- Cosine similarity vs distance — why text embeddings rarely produce negative scores
- pgvector — <=> operator, IVFFlat and HNSW indexing strategies

**Live services:**
- Supabase: 3 tables + Storage + match_items function + pgvector
- Telegram: Dropzone bot with full capture + nudge + review + commands
- OpenAI: GPT-4o-mini + Whisper + text-embedding-3-small
- SendGrid: weekly digest (Saturday + Sunday)
- Railway: deployed, auto-deploys from GitHub
