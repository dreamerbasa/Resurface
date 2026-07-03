from pipeline.extractors.url import extract

tests = [
    ("Substack", "https://aswathdamodaran.substack.com/p/just-do-it-brand-name-lessons-from"),
    ("YouTube with captions", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
    ("YouTube Short", "https://www.youtube.com/watch?v=xrDzWOHCBd8"),
    ("YouTube short link", "https://youtu.be/dQw4w9WgXcQ"),
    ("Instagram reel", "https://www.instagram.com/reel/DW2qPBuCvRk/"),
    ("Medium", "https://medium.com/free-code-camp/learn-python-by-building-projects-9e3b1b1a7941"),
    ("LinkedIn post", "https://www.linkedin.com/posts/arjenriezebosch_hiring-share-7478711681976709120-s1HZ/?utm_source=share&utm_medium=member_desktop&rcm=ACoAACmgTW0BPkVowFePhnzoQDtpT8_o6x1sBTA"),
    ("Random blog", "https://waitbutwhy.com/2018/04/picking-career.html"),
    ("URL in message", "hey check this https://waitbutwhy.com/2018/04/picking-career.html great read"),
    ("Dead URL", "https://thiswebsitedoesnotexist12345.com/article"),
]

for name, url in tests:
    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    print(f"{'='*60}")
    try:
        result = extract(url)
        print(f"Platform: {result.get('source_platform')}")
        print(f"Screenshot needed: {result.get('needs_screenshot', False)}")
        text = result.get('extracted_text') or 'None'
        print(f"Extracted: {text[:200]}...")
    except Exception as e:
        print(f"CRASHED: {type(e).__name__}: {e}")
