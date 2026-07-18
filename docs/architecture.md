# Personal Knowledge Aggregator — Architecture Document

## Project overview

A personal tool that aggregates scattered saves, screenshots, links, and ideas from multiple platforms into one intelligent system that organizes, connects, and resurfaces them for review.

**Project type:** Personal project + portfolio piece
**Goal:** Solve the "I saved it and forgot it" problem across Instagram, LinkedIn, Substack, Samsung Notes, and random thoughts.

---

## Step 1: High-level system architecture ✅

### Layers

**Input layer — Telegram bot (universal inbox)**
All content gets forwarded/shared/typed/voice-noted here. No habit changes required. Five source types: Instagram shares, screenshots (LinkedIn jobs, books, articles), Substack links, voice notes, plain text ideas.

**Processing layer — FastAPI backend, two-step pipeline**
- Step 1 (Extract): Format-specific, no intelligence. Vision API for images, web fetch for URLs, Whisper for voice, passthrough for text. Output = raw extracted content.
- Step 2 (Classify): Format-agnostic, all intelligence. Single LLM call, dynamic categories pulled from DB. Output = structured item (category, title, summary, tags, embedding).

**Storage layer — Supabase**
Postgres for structured data, pgvector for embedding similarity search. Categories are user-defined (CRUD via bot), not hardcoded.

**Intelligence layer — Scheduled jobs**
Generates embeddings, clusters related items across sources, scores items for resurfacing.

**Output layer — Two channels**
- Daily Telegram nudge: 2-3 items to revisit.
- Weekly email digest: themed clusters with action prompts.

**Feedback loop**
User actions on nudges (archive / remind later / acted on) update item status back in storage, influencing future resurfacing.

### External dependencies

| Service        | Purpose                          |
|----------------|----------------------------------|
| Claude API     | Vision (screenshot OCR) + classification |
| Whisper API    | Voice note transcription         |
| SendGrid       | Weekly email digest              |
| Supabase       | DB + vector search + file storage |
| Railway/Render | Hosting                          |

---

## Step 2: Data model ✅

### Table: `categories`

| Field       | Type      | Purpose                                                    |
|-------------|-----------|------------------------------------------------------------|
| id          | uuid      | Primary key                                                |
| name        | text      | Display name ("recipe", "job posting")                     |
| description | text      | Guides LLM classifier ("Food recipes, cooking instructions, meal ideas") |
| created_at  | timestamp | When created                                               |

User-defined and manageable via bot commands. Description field is critical — it's what the LLM reads to decide where content belongs.

### Table: `items`

**Raw input (what was sent to the bot):**

| Field           | Type     | Purpose                                       |
|-----------------|----------|-----------------------------------------------|
| id              | uuid     | Primary key                                   |
| content_type    | text     | image / url / voice / text                    |
| source_platform | text     | instagram / linkedin / substack / telegram    |
| raw_content     | text     | Original message text or URL                  |
| image_path      | text?    | Nullable. Reference to Supabase Storage for screenshots |

**Processed output (from the two-step pipeline):**

| Field          | Type     | Purpose                                       |
|----------------|----------|-----------------------------------------------|
| extracted_text | text     | Step 1 output — OCR text, article content, transcription |
| category_id    | uuid (FK)| References categories table                   |
| title          | text     | LLM-generated title                           |
| summary        | text     | 2-3 line summary                              |
| tags           | text[]   | Array column, not a join table                 |
| embedding      | vector   | pgvector column for similarity search          |
| processed_at   | timestamp? | Nullable. When step 1 + step 2 completed    |

**User ownership:**

| Field   | Type      | Purpose                          |
|---------|-----------|----------------------------------|
| user_id | uuid (FK) | References users table. Every item belongs to a user. |

**Resurfacing state:**

| Field            | Type       | Purpose                                    |
|------------------|------------|--------------------------------------------|
| status           | text       | fresh / surfaced / acted_on / archived     |
| interest         | integer    | User-rated 1-3, default 2                  |
| goal_alignment   | integer    | User-rated 1-3, default 1                  |
| times_surfaced   | integer    | Counter                                    |
| created_at       | timestamp  | When item was first saved                  |
| last_surfaced_at | timestamp? | Nullable. Last time this item was nudged   |
| resurface_after  | timestamp? | Nullable. For "remind me later" — sets a future date |

### Table: `users`

| Field             | Type       | Purpose                                              |
|-------------------|------------|------------------------------------------------------|
| id                | uuid       | Primary key                                          |
| telegram_user_id  | bigint     | Telegram's user ID, unique. Used for authorization.  |
| chat_id           | bigint     | Telegram chat ID. Auto-captured on /start. Used to send proactive messages (nudges, reminders). |
| display_name      | text       | User's Telegram first name                           |
| is_active         | boolean    | Default true. /stop sets false (pauses nudges), /start resumes. |
| reminder_time     | time       | User's preferred nightly reminder time. Default 22:00. Set via /remindertime. |
| nudge_time        | time       | User's preferred morning nudge time. Default 08:30. Set via /nudgetime. |
| created_at        | timestamp  | When user first sent /start                          |
| last_active_at    | timestamp  | Updated on every message. For staleness tracking, not automatic deactivation. |

**Multi-user design:**
- Chat ID is auto-captured when a user sends /start — no manual configuration.
- AUTHORIZED_USER_IDS in .env controls who can use the bot. Users table controls where to send messages.
- Adding a friend: add their Telegram user ID to AUTHORIZED_USER_IDS → they message bot → /start auto-creates their user record → nudges and reminders include them.
- Items are filtered by user_id for nudges, reminders, /review, /stats — each user only sees their own items.

### Storage cleanup policy

- **Images** (Supabase Storage): Deleted 72 hours after successful processing (`processed_at`). A weekly cleanup job handles this.
- **Text fields** (`raw_content`, `extracted_text`, `summary`): Kept permanently. Negligible storage footprint.
- **Decision for MVP:** Treat all image categories the same. Revisit if visual-heavy categories (recipes, places) need longer retention.

### Design rationale

- Tags as array column, not a separate table — no need for relational tag queries at scale.
- Clusters computed on the fly via pgvector similarity at digest time, not pre-stored.
- Feedback tracked as status updates on items, not a separate log table.
- Users table auto-populated via /start — no manual chat ID configuration.
- Reminder and nudge times stored per-user, not global config — each user sets their own schedule.
- is_active is a manual opt-in/opt-out, not automatic deactivation. last_active_at is informational only.
- Every skipped table is a migration not maintained.

---

## Step 3: Processing pipeline ✅

### Overview

Synchronous pipeline. No message queue, no background workers. Full flow takes ~4-6 seconds per item. Bot shows "typing..." indicator during processing. At 10-15 items/week volume, async infrastructure is unnecessary overhead.

### Flow: Message → Stored item

**1. Message arrives → Type detection (free)**

Telegram API already provides content type via message fields (`message.photo`, `message.voice`, `message.text`, `message.document`). Simple if-else routing, no AI call needed. If text contains a URL, route to URL processor.

**2. Step 1: Extract (format-specific, no intelligence)**

One of four paths fires based on content type:

| Content type | Processor | What it does | Output |
|---|---|---|---|
| Image | OpenAI GPT-4o-mini Vision | Downloads image from Telegram, uploads to Supabase Storage (temporary), sends to Vision API with prompt to extract text and describe image. Ignores UI noise (status bars, nav buttons, app chrome). If user sends a caption with the image, it's prepended as "User note:". | `extracted_text` (OCR + visual description), `image_path` |
| URL (Instagram) | Screenshot fallback | Instagram blocks all scraping (oEmbed, trafilatura). Skips fetching entirely, returns `needs_screenshot: True`. Bot asks user to send a screenshot instead. | No extraction — redirects to image path |
| URL (Medium) | Screenshot fallback | Medium blocks scraping similarly to Instagram. Same screenshot redirect. P3 enhancement (Issue 25) to explore RSS/headless browser. | No extraction — redirects to image path |
| URL (YouTube) | youtube-transcript-api + oEmbed | Extracts video ID from URL, fetches auto-generated captions via transcript API, gets title + author via oEmbed. If no captions (e.g. Shorts), falls back to title + author only. Truncates transcript to ~1000 words. | `extracted_text` (title + transcript or title-only), `source_platform = "youtube"` |
| URL (other) | trafilatura | Parses URL, detects source platform from domain, fetches with browser User-Agent, extracts clean article content via trafilatura with `favor_recall=True`. | `extracted_text` (truncated to ~1000 words), `source_platform` |
| Voice | OpenAI Whisper API | Downloads audio from Telegram, transcribes, deletes audio file after | `extracted_text` (full transcription) |
| Text | Passthrough | No API call | `extracted_text` = `raw_content` |

The URL extractor has a sub-router: detect domain → Instagram/Medium → screenshot fallback; YouTube → transcript API + oEmbed; everything else → trafilatura. If a message contains multiple URLs, each is extracted and classified separately.

**User notes:** Both URL and image messages can include user text alongside the content. For URLs, the surrounding message text is captured as a user note and prepended to extracted_text. For images, the Telegram caption serves the same purpose. This gives the classifier better context (e.g. "must try this recipe" + article content → stronger recipe classification).

**Storage rules for extracted_text:**

- Images: store full OCR output (naturally short).
- Voice: store full transcription (voice notes are typically short).
- Text: store full content.
- URLs: truncate to ~1000 words. Full content is only used as input to step 2, then discarded. Original URL in `raw_content` serves as permanent reference.

**3. Step 2: Classify (format-agnostic, all intelligence)**

Single LLM call, same for all content types:

- Pull current categories + descriptions from Supabase.
- Construct prompt with category list and extracted content.
- LLM returns JSON: `category`, `title`, `summary` (2-3 lines), `tags[]` (3-5 tags).
- If no category fits, returns `uncategorized` + suggested new category name.

**4. Generate embedding**

Concatenate `title + summary + tags` and generate embedding vector. Uses processed summary, not raw extracted text — semantically cleaner, produces sharper similarity clusters. Done synchronously as part of the pipeline.

**5. Store (single DB insert)**

One insert into `items` table. Sets `status = 'fresh'`, `times_surfaced = 0`, `processed_at = now()`.

**6. Acknowledge to user**

Bot replies: "Saved under [category]: [title]" with tags shown. If classifier returned `uncategorized`: "Saved this but wasn't sure where it goes — closest match is [X]. Reply to recategorize."

### Design decisions

| Decision | Choice | Rationale |
|---|---|---|
| Sync vs async | Synchronous | ~5 sec wait is fine for 2 items/day. No queue/worker infrastructure to maintain. |
| URL parser | trafilatura | Purpose-built for article extraction. Handles Substack, Medium, blogs out of the box. |
| Embedding source | title + summary + tags | Processed content is more semantically meaningful than raw OCR. Sharper clusters. |
| Error handling | Store with status "processing_failed" | No retry queue for MVP. Manual retry via bot command is sufficient. |

### Edge cases

- Instagram shares come as URLs (instagram.com/reel/... or instagram.com/p/...) when shared via Telegram, not as images. They route through the URL extractor's Instagram sub-path (oEmbed API for caption extraction). If the caption is empty or too short, bot suggests sending a screenshot instead.
- Instagram reel video transcription (extracting what someone says in the reel) is a future enhancement — requires downloading video, extracting audio, and transcribing. Deferred to Milestone 5.
- LinkedIn screenshots are images — they route through the Vision API path.
- Substack and other article links route through trafilatura.
- Unsupported formats (video, documents, stickers) get a fallback message: "I can't process this format yet. Try sending a screenshot or text instead."

---

## Step 4: Resurfacing logic ✅

The core product value. Without this, the project is a filing cabinet. With it, the system actively thinks about your saved content and brings the right things back at the right time.

### 4.1 User inputs at capture time

After the bot acknowledges a save, it shows two rows of quick-reply buttons:

- Interest: 🔥 High (3) · 👍 Medium (2) · 🤷 Low (1)
- Goal alignment: 🎯 Aligned (3) · ↔️ Somewhat (2) · ❌ Nope (1)

Two taps, done. If no response within a minute or next item is sent, defaults to interest = 2, goal_alignment = 1. Zero friction for quick-fire saves, richer data when the user has a moment.

**New fields on items table:**

| Field          | Type    | Default |
|----------------|---------|---------|
| interest       | integer | 2       |
| goal_alignment | integer | 1       |

### 4.2 Resurfacing approach — Lifecycle phases (revised)

Originally designed as a pure scoring formula (base_matrix + age_boost + fresh_bonus + never_seen_escalation - surfacing_penalty + cooldown). Replaced with lifecycle phases after discovering scoring was fragile — age-based bonuses dominated, weight tuning was a rabbit hole, and behavior was unpredictable.

Lifecycle approach maps directly to user expectations: each rule is independently understandable and testable.

**Phase 1: First appearance (times_surfaced = 0, < 7 days old)**

Every item surfaces at least once within 7 days. When it surfaces depends on priority:

| Priority weight | First surfaces by |
|---|---|
| 7-9 (high) | Day 2 |
| 5-6 (medium) | Day 4 |
| 2-4 (low-medium) | Day 6 |
| 1 (lowest) | Day 7 |

Priority weight comes from the 3×3 matrix:

| | 🎯 High goal (3) | ↔️ Medium goal (2) | ❌ Low goal (1) |
|---|---|---|---|
| **🔥 High interest (3)** | 9 (Priority) | 6 (Regular) | 4 (Leisure) |
| **👍 Medium interest (2)** | 8 (Push) | 5 (Standard) | 2 (Low priority) |
| **🤷 Low interest (1)** | 7 (Nag) | 3 (Fading) | 1 (Dead weight) |

An item is "overdue" if days_old >= its max_days threshold and times_surfaced is still 0.

**Phase 2: Active resurfacing (surfaced 1-3 times)**

Items compete on matrix_weight score. 3-day cooldown: skip if last_surfaced_at was within 3 days (escalation candidates with times_surfaced >= 3 ignore cooldown). Higher score = picked first.

**Phase 3: Decay (surfaced 3+ times, no action)**

ONLY for goal_alignment 1 or 2. High-goal items (goal_alignment = 3) NEVER decay — they stay in Phase 2 permanently until user acts.

| Surface count | Next appearance |
|---|---|
| After 3rd | resurface_after = now + 7 days |
| After 4th | resurface_after = now + 30 days |
| After 5th | Excluded from nudges permanently. Only in /review and weekly digest. |

**Daily selection: 3 fixed slots**

| Slot | Fills with | Fallback if empty |
|---|---|---|
| Slot 1 (new) | Oldest unsurfaced Phase 1 item. Overdue items first. | Highest scored Phase 2 item |
| Slot 2 (priority) | Highest scored Phase 2 item | Next Phase 1 item |
| Slot 3 (flexible) | Most overdue Phase 1 item if any exist, otherwise highest interest item from either pool (the "treat") | Whatever remains |

Emoji mapping: 🆕 = Phase 1 first surface, ⚠️ = escalation (3+ surfaces), 🎯 = high goal, 🔥 = high interest, 👍 = standard.

**Weekend catch-up (Sat-Sun):**

If Phase 1 items > 3 on a weekend, switch to catch-up mode: show up to 5 unsurfaced items (oldest first) instead of normal 3-slot system. Actively clears the backlog.

**Why lifecycle over scoring:** Started with pure scoring, found it fragile. Age bonus dominated everything. Weight tuning was a rabbit hole with unpredictable emergent behavior. Lifecycle rules map to explicit user expectations: "new things surface within a week, old things fade unless important, stop nagging about stuff I don't care about." Each rule is testable independently.

### Open questions (to revisit after real usage)

**Q: Is it better to surface items within the first 7 days or after 7 days?**
Current design assumes items should surface quickly (within 7 days). But there's a case for delayed resurfacing — letting items "age" so when they come back, you've forgotten the initial impulse and can evaluate them more objectively. Needs real usage data to decide. Logging this for review after 2-3 weeks of using the nudge system.

### 4.3 Cadence — WHEN it surfaces

### 4.3 Cadence — WHEN it surfaces

| Channel | Frequency | Content | Purpose |
|---|---|---|---|
| Telegram nudge | Daily | 2-3 individual items, scored by priority matrix | Quick revisit, keep things moving |
| Email digest | Weekly | Themed clusters + standalones + cleanup corner | Deep review, see patterns, prune dead weight |

### 4.4 Clustering — HOW things are grouped (weekly digest)

**Approach: similarity threshold grouping using pgvector.**

At digest time, take all active items (status = fresh or surfaced). For each item, query pgvector for other items with cosine similarity > 0.75. Connected items form a cluster. Items with no close neighbors stay as standalone singles. No need to predefine number of clusters — the data determines natural groupings.

**Scope: full history, not just current week.** Clusters form across the entire active item set, including older items. This enables long-range connections: "You saved a business idea about data infrastructure 2 months ago and a Substack article about the same space this week — still interested?" Recent items are weighted higher in digest presentation.

**Cluster naming:** feed titles and summaries of clustered items to an LLM prompt — "These items were saved across different platforms over time. What's the common theme? Give it a short name." Output: "Bangalore café exploration" or "Fintech career opportunities."

### 4.5 Weekly digest structure

**Section 1 — Themed clusters.**
"You have 4 items about [theme]. Here they are together." Cross-source connections no single app can make. Each cluster shows the theme name, individual items with their source platforms, and action buttons.

**Section 2 — Standalone items.**
Items that didn't cluster with anything. Shown individually, sorted by priority matrix score.

**Section 3 — Cleanup corner.**
Items 3+ weeks old with low interest and low goal alignment (the "dead weight" cell). "Archive these? You're probably not coming back to them." Quick archive buttons for each.

---

## Step 5: Bot interface design ✅

### 5.1 Single-bot architecture (revised)

**Decision:** One bot (Dropzone) handles everything — capture, nudges, reminders, review, and commands.

Originally planned as two bots (CaptureBot + NudgeBot) to separate capture noise from nudges. Revised to a single bot because:
- Low volume (~7 saves/day + 2 system messages) doesn't create real clutter.
- Shareability: explaining two bots to friends is friction. One bot is a simple pitch.
- The "review" need is better solved by a live DB query (command or pinned message) than by a separate chat's history.

**Key insight:** Two bots gives you a chat log. A `/review` command gives you a live queue. A live queue is what "review" actually means — you want to see what's still open now, not re-read old nudges. Everything is a DB query against item status; no sent messages are stored.

### 5.2 Persistent nudge design (the core product mechanic)

The failure mode to avoid: nudge fires → user glances → doesn't act → nudge scrolls up in chat → forgotten forever. This just moves the graveyard from the gallery to Telegram.

Three mechanisms solve this together:

1. **Nudges repeat until acted upon.** An item doesn't disappear after one nudge. It keeps surfacing (with decreasing frequency if repeatedly ignored) until the user taps Archive / Done / Remind later. The nudge is a persistent open loop, not fire-and-forget. After N ignores, it escalates to a decision prompt: "You've skipped this 3 times. Keep it or drop it?"

2. **`/review` command.** A live queue pulled up on demand. Queries the DB for items with status = surfaced (pending action), shows them with action buttons. Always current, nothing stored.

3. **Weekly digest.** The deeper review — themed clusters, cleanup corner, full picture. Catches anything daily nudges didn't resolve.

Item status (fresh / surfaced / acted_on / archived) is the single source of truth. Nudges point the user at items in a given state.

### 5.2 Capture flow (You → CaptureBot)

**Single item save:**

1. User sends image / URL / voice note / text to CaptureBot.
2. Bot shows typing indicator (~5 sec while pipeline runs).
3. Bot replies: "Saved under [category]: [title]" with tags.
4. Bot shows rating buttons:
   - Interest: 🔥 High · 👍 Medium · 🤷 Low
   - Goal fit: 🎯 Aligned · ↔️ Somewhat · ❌ Nope
   - ⏰ Remind tonight (optional — flags item to resurface in the nightly reminder)
5. If no response within 1 minute or next item sent, defaults apply (interest=2, goal_alignment=1).
6. If classifier returned `uncategorized`: "Saved this but wasn't sure — closest match is [X]. Reply to recategorize."

**Batch save (multiple items at once):**

- Multiple photos: Telegram sends as media group (shared `media_group_id`). Bot collects all, processes each as separate item.
- Multiple URLs in one message: Bot parses text, extracts all URLs, creates separate items.
- Bot replies with numbered summary:
  1. Recipe: Butter chicken reel
  2. Job: PM role at Razorpay
  3. Book: Atomic Habits recommendation
- "Tap any to rate, or I'll default to 👍/❌ for all."
- Each title is a clickable button for optional individual rating.

**Content routing (automatic, no configuration on Telegram side):**

| Telegram message type | Pipeline route |
|---|---|
| `message.photo` | Image → Vision API |
| `message.voice` | Voice → Whisper |
| `message.text` with URL | URL → trafilatura |
| `message.text` without URL | Text → passthrough |
| Media group | Each photo processed separately |

Sharing to CaptureBot works like WhatsApp — tap Share on any app (Instagram, browser, gallery, LinkedIn), pick the CaptureBot chat, send.

### 5.3 Nudge design

**Daily morning nudge (default 8:30 AM, configurable):**

Format per item: emoji (maps to priority matrix) + title + category + age + one-line context + action buttons.

Priority emoji mapping:
- 🎯 = high goal alignment (push/nag items)
- 🔥 = high interest
- 👍 = standard
- ⚠️ = seen 3+ times, escalation candidate

Action buttons per item:
- `Archive` — done with this, never show again
- `Remind later` — resurface in 3 days (sets `resurface_after`)
- `Done` — acted on this (marks `acted_on`)
- `Open link` — shown only for items with a source URL, opens original content

2-3 items per nudge, selected by the scoring algorithm from the priority matrix.

**Persistent nudge behavior (items don't disappear when ignored):**
- Day 1, 2: item reappears in next day's nudge if not acted on
- Day 3 (3rd ignore): escalates — "You've seen this 3 times and haven't acted. Keep it or let it go?" with only two buttons: `Keep` (resets counter, surfaces again in 7 days) or `Drop` (archives it)
- `times_surfaced` counter on each item tracks this

**Pinned review queue:**

A single pinned message in the Dropzone chat, always at the top. Edited in place (not a new message) every morning after the scoring job runs. Always shows current state.

Format:
```
📋 Your Review Queue — 5 items pending

🎯 PM role at Razorpay (12 days, seen 2x)
🔥 Specialty coffee Indiranagar (3 days)
👍 Atomic Habits recommendation (8 days, seen 1x)
⚠️ Data infra business idea (21 days, seen 3x — decide?)
👍 Finshots article on RBI (5 days)

Tap /review to act on these
Last updated: today 8:30 AM
```

Design rules:
- Shows count of pending items
- Each item with priority emoji, title, age, times surfaced
- ⚠️ flag for items at 3+ ignores
- Last updated timestamp
- `/review` call to action
- Updated by editing the same message, never sending a new one — zero clutter
- Does NOT replace the daily nudge — the nudge is the prompt to act (with inline buttons), the pinned message is the persistent overview

Purpose: keeps user accountable, quick to review at a glance, always visible even when new saves push things up in chat.

**Nightly reminder (default 10 PM, configurable):**

Light prompt to encourage capture habit:
- On active days: "You saved X items today. Anything else on your mind before the day ends?"
- On zero-capture days: "Nothing saved today — quiet day or just forgot? Drop anything here before it slips away."

If any items have `remind_tonight = true` for this user, include a section:
```
📌 You wanted to revisit tonight:
• Building Workspaces for Financial Agents
• PM role at Snabbit
```
After the reminder fires, reset `remind_tonight = false` on those items.

**"Remind tonight" flow:** User saves an article → taps ⏰ Remind tonight → item flagged → nightly reminder includes it → flag cleared. No new scheduler. Piggybacks on existing nightly reminder.

**Weekly email digest (Sunday evening or Monday morning):**

Sent via SendGrid. Five sections:

- **Section 1 — Themed clusters:** Related items grouped by embedding similarity. Each cluster has a LLM-generated theme name, lists all items with source platforms, and offers "Explore this theme" or "Archive all" actions.
- **Section 2 — Deep dives:** Items the user flagged with "Go deep" during the week. For each, the LLM generates a structured learning roadmap from the article's extracted_text: key concepts, step-by-step learning path from scratch, related topics to explore. After digest sends, reset `go_deep = false`.
- **Section 3 — Standalone items:** Unclustered items, sorted by priority score. Same format as daily nudge items.
- **Section 4 — Cleanup corner:** Items 3+ weeks old, low interest, low goal alignment. "Archive these?" with one-tap archive buttons.
- **Section 5 — Quick stats:** "This week: X saved, Y acted on, Z archived. Total active items: N across M categories."

**"Go deep" flow:** User reads a nudge/review item → taps 🧠 Go deep → item flagged in DB → weekly digest generates a learning roadmap from the article content → includes it in the "Deep dives" section → flag cleared. No immediate action, no extra LLM calls during the week.

### 5.4 Nudge detail view — action buttons

**Normal items:**
[✅ Done] [📦 Archive] [⏰ Later]
[🔗 Read article] (URL items only)
[🧠 Go deep] (articles/content worth deep-diving)
[← Back to list]

**Escalation items (times_surfaced >= 3):**
[Keep — remind in 7 days] [Drop — archive it]

### 5.5 Additional data fields for new features

| Field | Type | Default | Purpose |
|---|---|---|---|
| remind_tonight | boolean | false | Flag for nightly reminder inclusion |
| go_deep | boolean | false | Flag for weekly digest deep dive generation |

### 5.4 Bot commands (MVP, all in Dropzone)

| Command | What it does |
|---|---|
| `/start` | First-time setup. Creates default categories, sets nudge times. |
| `/addcategory name \| description` | Create a new category with LLM-facing description. |
| `/categories` | List all categories with item counts. |
| `/review` | Live review queue — shows all pending items with action buttons. |
| `/review 7` | Show items from last 7 days, grouped by category. |
| `/search coffee` | Keyword search across titles, summaries, and tags. |
| `/stats` | Total active items, by category, saved/acted/archived this week and month. |
| `/nudgetime 8:30` | Set daily nudge time. |
| `/help` | List all commands with short descriptions. |

---

## Step 6: Tech stack + deployment ✅

### Stack choices

| Component | Choice | Why |
|---|---|---|
| Language | Python | Known language, best AI/ML ecosystem, all libraries available |
| Web framework | FastAPI | Lightweight, async-capable, auto-generates API docs, modern portfolio piece |
| Telegram library | python-telegram-bot | Most popular, best documented, supports inline keyboards, media groups, polling + webhook |
| Database | Supabase (Postgres + pgvector) | Free tier: 500MB DB + 1GB file storage + vector search. Managed, no self-hosting. |
| LLM (classification) | OpenAI GPT (via existing credits) | Started with Gemini free tier, switched to OpenAI ($3 existing balance). Reliable JSON output. |
| Vision (screenshots) | OpenAI GPT-4o-mini Vision | ~$0.01/image. Handles OCR + visual description in one call. Filters UI noise. |
| Voice transcription | OpenAI Whisper API | Best accuracy, $0.006/min. Same provider as classification. |
| Embeddings | OpenAI text-embedding-3-small | $0.02/1M tokens. Industry standard for vector search. |
| URL extraction | trafilatura + youtube-transcript-api | trafilatura for articles/blogs. YouTube transcript API for video captions. Both free, no API keys. |
| Email | SendGrid | Free tier: 100 emails/day. Mature Python SDK, HTML templates. |
| Scheduler | APScheduler | Runs inside FastAPI process. No external cron service needed. |
| Hosting | Railway | GitHub push-to-deploy. Start with polling mode on free tier, upgrade to $5/month for always-on if needed. |

### Repo structure

```
knowledge-aggregator/
├── bot/
│   ├── capture_bot.py          # CaptureBot handlers
│   ├── nudge_bot.py            # NudgeBot handlers
│   └── keyboards.py           # Inline keyboard layouts
├── pipeline/
│   ├── router.py               # Content type detection + routing
│   ├── extractors/
│   │   ├── vision.py           # Claude Vision API
│   │   ├── url.py              # trafilatura
│   │   ├── whisper.py          # Whisper transcription
│   │   └── text.py             # Passthrough
│   └── classifier.py           # LLM classification step 2
├── intelligence/
│   ├── embeddings.py           # Embedding generation
│   ├── scoring.py              # Priority matrix scoring
│   └── clustering.py           # Similarity clustering
├── notifications/
│   ├── daily_nudge.py          # Morning nudge generation
│   ├── nightly_reminder.py     # Evening capture prompt
│   └── weekly_digest.py        # Email digest builder
├── db/
│   ├── models.py               # Table models
│   ├── queries.py              # DB query functions
│   └── storage.py              # Supabase file storage
├── config.py                   # Env variables, settings
├── scheduler.py                # APScheduler setup
├── main.py                     # App entry point
├── requirements.txt
├── .env.example
└── README.md
```

### Monthly cost estimate

| Component | Cost |
|---|---|
| OpenAI GPT (classification + vision) | ~₹50-80 |
| OpenAI Whisper (voice transcription) | ~₹10-20 |
| OpenAI embeddings (future) | ~₹5-10 |
| Supabase | Free tier |
| SendGrid | Free tier |
| Railway (polling mode) | Free tier |
| **Total** | **~₹65-110/month** |
