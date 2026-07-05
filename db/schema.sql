-- 1. Categories table
CREATE TABLE categories (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 2. Items table (weekend 1 fields only)
CREATE TABLE items (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    content_type TEXT NOT NULL CHECK (content_type IN ('image', 'url', 'voice', 'text')),
    raw_content TEXT NOT NULL,
    extracted_text TEXT,
    category_id UUID REFERENCES categories(id),
    title TEXT,
    summary TEXT,
    tags TEXT[],
    status TEXT DEFAULT 'fresh' CHECK (status IN ('fresh', 'surfaced', 'acted_on', 'archived')),
    created_at TIMESTAMPTZ DEFAULT now(),
    processed_at TIMESTAMPTZ,
    image_path TEXT,
    interest INTEGER DEFAULT 2,
    goal_alignment INTEGER DEFAULT 1,
    user_id UUID REFERENCES users(id),
    times_surfaced INTEGER DEFAULT 0,
    last_surfaced_at TIMESTAMPTZ,
    resurface_after TIMESTAMPTZ
);

-- 3. Seed default categories
INSERT INTO categories (name, description) VALUES
    ('recipe', 'Food recipes, cooking instructions, meal ideas, ingredients lists'),
    ('job_posting', 'Job listings, hiring posts, role descriptions, career opportunities'),
    ('business_idea', 'Startup concepts, side hustle ideas, product gaps, business opportunities'),
    ('poem', 'Poetry, verse, spoken word pieces, lyrical writing, creative fragments'),
    ('article_to_read', 'Articles, blog posts, newsletters, long-form content to read later'),
    ('book_to_read', 'Book recommendations, reading list additions, book reviews'),
    ('place_to_visit', 'Restaurants, cafes, travel destinations, places to explore'),
    ('motivation', 'Motivational quotes, inspiring posts, life advice'),
    ('song', 'Music recommendations, songs to listen to, playlists'),
    ('random_thought', 'Miscellaneous ideas, observations, thoughts that do not fit other categories');

-- Users Table
CREATE TABLE users (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    telegram_user_id BIGINT NOT NULL UNIQUE,
    chat_id BIGINT NOT NULL,
    display_name TEXT,
    is_active BOOLEAN DEFAULT true,
    reminder_time TIME DEFAULT '22:00',
    nudge_time TIME DEFAULT '08:30',
    created_at TIMESTAMPTZ DEFAULT now(),
    last_active_at TIMESTAMPTZ DEFAULT now()
);