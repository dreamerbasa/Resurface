# Resurface — Weekend 1 Code Overview

## How the pieces connect

```
test_pipeline.py (you run this)
    │
    ▼
pipeline/router.py (orchestrator — calls everything in order)
    │
    ├──► pipeline/extractors/text.py (step 1: extract)
    │
    ├──► pipeline/classifier.py (step 2: classify)
    │         │
    │         ├──► db/queries.py → get_categories() (reads from Supabase)
    │         └──► config.py → Anthropic client (calls Claude API)
    │
    └──► db/queries.py → insert_item() (writes to Supabase)
```

Everything starts from `router.py`. It calls the extractor, then the classifier, then stores the result. The test script just feeds it sample messages so you can verify without Telegram.

---

## File-by-file breakdown

### 1. `config.py`

**What it is:** The settings file. Every other file imports from here instead of reading `.env` directly.

**What it does:**
- Reads your `.env` file (Supabase URL, Supabase key, Anthropic API key).
- Creates a Supabase client (the connection to your database).
- Creates an Anthropic client (the connection to Claude API).
- If any key is missing, it throws a clear error so you know what to fix.

**Why it exists:** Without this, every file would have its own `dotenv.load()` call and its own client initialization. Centralizing it means one place to update if keys change, and no duplicate connections.

**Depends on:** Nothing (this is the base layer).
**Used by:** Everything else.

---

### 2. `db/queries.py`

**What it is:** The database layer. All reads and writes to Supabase go through here.

**What it does — two functions:**

**`get_categories()`**
- Reads all rows from the `categories` table in Supabase.
- Returns a list like:
  ```python
  [
      {"id": "uuid-1", "name": "recipe", "description": "Food recipes, cooking..."},
      {"id": "uuid-2", "name": "job_posting", "description": "Job listings..."},
      ...
  ]
  ```
- The classifier needs this to know what categories exist and what they mean.

**`insert_item(data)`**
- Takes a dict with all the processed fields (content_type, raw_content, extracted_text, category_id, title, summary, tags, status, processed_at).
- Inserts it as a new row in the `items` table.
- Returns the inserted row.

**Why it exists:** Keeps all database logic in one place. If you ever change how you query Supabase (different table name, different fields), you change it here, not in 5 different files.

**Depends on:** `config.py` (for the Supabase client).
**Used by:** `classifier.py` (reads categories), `router.py` (inserts items).

---

### 3. `pipeline/extractors/text.py`

**What it is:** The simplest extractor. Handles plain text messages.

**What it does — one function:**

**`extract(raw_content)`**
- Takes the raw text you sent.
- Returns it wrapped in a structured dict:
  ```python
  {
      "content_type": "text",
      "raw_content": "startup idea: data for quant funds",
      "extracted_text": "startup idea: data for quant funds",
      "source_platform": "telegram"
  }
  ```
- No API calls, no processing. It literally passes the text through.

**Why it exists (if it does nothing):** Architecture consistency. In weekend 2, you'll add `vision.py` (calls Claude Vision API for screenshots), `url.py` (calls trafilatura for links), and `whisper.py` (calls Whisper for voice notes). All extractors have the same interface: take raw input → return a dict with `extracted_text`. The router doesn't care which extractor ran — it just passes `extracted_text` to the classifier. If the text extractor didn't exist, the router would need an if-else saying "if text, skip extraction" — that's a special case that makes the code messier.

**Depends on:** Nothing.
**Used by:** `router.py`.

---

### 4. `pipeline/classifier.py`

**What it is:** The brain. This is where AI happens.

**What it does — one function:**

**`classify(extracted_text)`**

Step by step:

1. **Fetches categories from the database.** Calls `get_categories()` to get the current list of categories with their names and descriptions. This makes the classifier dynamic — if you add a new category tomorrow, the classifier automatically starts using it. No code change needed.

2. **Builds the prompt.** Creates a message for Claude that says: "Here are the categories: [list with descriptions]. Here's the content: [extracted text]. Classify it. Return JSON."

3. **Calls Claude Sonnet API.** Sends the prompt and gets back a JSON response like:
   ```json
   {
       "category_name": "business_idea",
       "title": "Survivorship-bias-free data for quant funds",
       "summary": "An idea for providing clean historical constituent data...",
       "tags": ["quant", "data", "fintech", "india"]
   }
   ```

4. **Parses the JSON.** Extracts the fields from Claude's response. Handles edge cases where Claude might wrap the JSON in markdown backticks.

5. **Looks up the category_id.** Claude returns a category *name* (like "business_idea"), but the database needs a category *UUID*. So it matches the name against the fetched categories to find the corresponding UUID.

6. **Returns the structured result:**
   ```python
   {
       "category_id": "uuid-of-business-idea",
       "category_name": "business_idea",
       "title": "Survivorship-bias-free data for quant funds",
       "summary": "An idea for providing...",
       "tags": ["quant", "data", "fintech", "india"]
   }
   ```

**Why it exists:** This is the core intelligence of the project. Everything else is plumbing — this is the step where raw text becomes structured, categorized knowledge.

**Depends on:** `config.py` (Anthropic client), `db/queries.py` (fetches categories).
**Used by:** `router.py`.

---

### 5. `pipeline/router.py`

**What it is:** The orchestrator. It runs the full pipeline in order.

**What it does — one function:**

**`process_message(raw_content, content_type="text")`**

Step by step:

1. **Picks the right extractor** based on `content_type`. For now, only "text" is supported. In weekend 2, "image" → vision.py, "url" → url.py, "voice" → whisper.py.

2. **Calls the extractor.** Gets back `extracted_text` and metadata.

3. **Calls the classifier.** Passes `extracted_text`, gets back category, title, summary, tags.

4. **Merges everything** into one dict combining extractor output + classifier output + timestamp.

5. **Inserts into database** by calling `insert_item()`.

6. **Returns the result** so the bot (or test script) can show the acknowledgment.

**Why it exists:** The bot shouldn't know about extractors, classifiers, or database queries. It just calls `process_message("some text")` and gets back a result. The router handles the internal choreography. This also means when you add new content types, you only change the router — the bot code stays the same.

**Depends on:** `pipeline/extractors/text.py`, `pipeline/classifier.py`, `db/queries.py`.
**Used by:** The bot (weekend 2+), `test_pipeline.py` (for now).

---

### 6. `test_pipeline.py`

**What it is:** A temporary test script to verify everything works without Telegram.

**What it does:**
- Has 3 hardcoded test messages (a business idea, a place recommendation, a poem fragment).
- Runs each through `process_message()`.
- Prints the result (what category it was classified as, the title, summary, tags).
- If all 3 succeed, you check Supabase dashboard and should see 3 new rows in the `items` table.

**Why it exists:** Telegram is blocked, and even when it's not, you want to test the pipeline independently of the bot. If something breaks, this script tells you whether the problem is in the pipeline or in the bot layer.

**Depends on:** `pipeline/router.py` (which pulls in everything else).
**Used by:** You, from the command line: `python test_pipeline.py`.

---

## The data flow for one message

Here is what happens when you send "try the new ramen place in koramangala":

```
Input: "try the new ramen place in koramangala"
                    │
         ┌──────────▼──────────┐
         │  text.py extract()  │
         │  passthrough — no   │
         │  processing needed  │
         └──────────┬──────────┘
                    │
    extracted_text: "try the new ramen place in koramangala"
                    │
         ┌──────────▼──────────┐
         │  classifier.py      │
         │  1. fetch categories│
         │  2. build prompt    │
         │  3. call Claude API │
         │  4. parse response  │
         └──────────┬──────────┘
                    │
    result: {
        category_name: "place_to_visit",
        title: "Ramen place in Koramangala",
        summary: "A recommendation to try a new ramen restaurant...",
        tags: ["food", "koramangala", "ramen", "restaurant"]
    }
                    │
         ┌──────────▼──────────┐
         │  queries.py         │
         │  insert_item()      │
         │  → Supabase items   │
         └──────────┬──────────┘
                    │
    Stored in database ✓
    Bot replies: "Saved under place_to_visit: Ramen place in Koramangala"
```
