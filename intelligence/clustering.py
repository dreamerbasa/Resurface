import json
import re
import warnings
from datetime import datetime, timezone

warnings.filterwarnings("ignore", category=FutureWarning, module="sklearn")

import numpy as np
from sklearn.cluster import HDBSCAN
from sklearn.metrics.pairwise import cosine_distances

from config import supabase, openai_client
from intelligence.scoring import _extract_url


def _fetch_items_with_embeddings(user_id: str) -> list[dict]:
    response = (
        supabase.table("items")
        .select("id, title, summary, content_type, raw_content, interest, goal_alignment, times_surfaced, tags, created_at, embedding, categories(name)")
        .eq("user_id", user_id)
        .in_("status", ["fresh", "surfaced"])
        .not_.is_("embedding", "null")
        .execute()
    )
    now = datetime.now(timezone.utc)
    items = []
    for item in response.data:
        cat = item.pop("categories", None)
        from dateutil.parser import isoparse
        created_at = isoparse(item["created_at"]) if item.get("created_at") else now
        age_days = (now - created_at).total_seconds() / 86400

        items.append({
            "id": item["id"],
            "title": item.get("title") or "Untitled",
            "summary": item.get("summary") or "",
            "category_name": cat["name"] if cat else None,
            "content_type": item.get("content_type"),
            "raw_content": item.get("raw_content"),
            "interest": item.get("interest") or 2,
            "goal_alignment": item.get("goal_alignment") or 1,
            "times_surfaced": item.get("times_surfaced") or 0,
            "tags": item.get("tags") or [],
            "age_days": round(age_days, 1),
            "url": _extract_url(item.get("raw_content")) if item.get("content_type") == "url" else None,
            "embedding": item["embedding"],
        })
    return items


def _generate_theme(items: list[dict]) -> dict:
    if not openai_client:
        return {"emoji": "📌", "theme": "Related items"}

    item_lines = "\n".join(f"- {i['title']}: {i['summary']}" for i in items)
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a theme naming assistant. Given a list of saved items, "
                        "identify their common theme. Respond with ONLY a JSON object: "
                        '{"emoji": "one relevant emoji", "theme": "2-5 word theme name"}. '
                        "No other text."
                    ),
                },
                {"role": "user", "content": f"Items:\n{item_lines}"},
            ],
            temperature=0.3,
        )
        text = response.choices[0].message.content.strip()
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            parsed = json.loads(match.group())
            return {
                "emoji": parsed.get("emoji", "📌"),
                "theme": parsed.get("theme", "Related items"),
            }
    except Exception as e:
        print(f"Theme naming failed: {type(e).__name__}: {e}")

    return {"emoji": "📌", "theme": "Related items"}


def _format_item(item: dict) -> dict:
    return {
        "id": item["id"],
        "title": item["title"],
        "summary": item["summary"],
        "category_name": item["category_name"],
        "content_type": item["content_type"],
        "age_days": item["age_days"],
        "interest": item["interest"],
        "goal_alignment": item["goal_alignment"],
        "url": item["url"],
    }


def cluster_items(user_id: str) -> dict:
    items = _fetch_items_with_embeddings(user_id)

    if len(items) < 2:
        return {
            "clusters": [],
            "standalone": [_format_item(i) for i in items],
            "total_items": len(items),
            "total_clusters": 0,
        }

    def _parse_embedding(emb):
        if isinstance(emb, str):
            return json.loads(emb)
        return emb

    embeddings_matrix = np.array([_parse_embedding(i["embedding"]) for i in items], dtype=np.float64)
    distance_matrix = cosine_distances(embeddings_matrix)

    clustering = HDBSCAN(
        min_cluster_size=2,
        metric="precomputed",
    ).fit(distance_matrix)

    cluster_groups = {}
    standalone = []

    for idx, label in enumerate(clustering.labels_):
        if label == -1:
            standalone.append(items[idx])
        else:
            if label not in cluster_groups:
                cluster_groups[label] = []
            cluster_groups[label].append(items[idx])

    clusters = []
    for label in sorted(cluster_groups, key=lambda l: -len(cluster_groups[l])):
        group = cluster_groups[label]
        theme_info = _generate_theme(group)
        clusters.append({
            "theme": theme_info["theme"],
            "emoji": theme_info["emoji"],
            "items": [_format_item(i) for i in group],
        })

    standalone.sort(key=lambda x: -x["interest"])

    return {
        "clusters": clusters,
        "standalone": [_format_item(i) for i in standalone],
        "total_items": len(items),
        "total_clusters": len(clusters),
    }
