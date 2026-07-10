import time

from config import supabase
from intelligence.embeddings import build_embedding_text, generate_embedding
from db.queries import update_item_embedding


def backfill():
    response = (
        supabase.table("items")
        .select("id, title, summary, tags")
        .is_("embedding", "null")
        .execute()
    )
    items = response.data
    total = len(items)
    print(f"Found {total} items without embeddings")

    for n, item in enumerate(items, 1):
        text = build_embedding_text(item.get("title"), item.get("summary"), item.get("tags"))
        if not text:
            print(f"Skipped {n}/{total}: {item.get('title', 'Untitled')} — no text to embed")
            continue

        embedding = generate_embedding(text)
        if embedding:
            update_item_embedding(item["id"], embedding)
            print(f"Embedded {n}/{total}: {item.get('title', 'Untitled')}")
        else:
            print(f"Failed {n}/{total}: {item.get('title', 'Untitled')}")

        if n < total:
            time.sleep(0.5)

    print("Backfill complete")


if __name__ == "__main__":
    backfill()
