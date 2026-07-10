from datetime import datetime, timezone, timedelta

from config import supabase

IST = timezone(timedelta(hours=5, minutes=30))


def get_categories():
    response = supabase.table("categories").select("id, name, description").execute()
    return response.data


def insert_item(data: dict):
    response = supabase.table("items").insert(data).execute()
    return response.data[0]


def update_item_rating(item_id: str, field: str, value: int):
    if field not in ("interest", "goal_alignment"):
        raise ValueError(f"Invalid field: {field}")
    supabase.table("items").update({field: value}).eq("id", item_id).execute()


def get_item(item_id: str):
    response = supabase.table("items").select("interest, goal_alignment").eq("id", item_id).execute()
    return response.data[0] if response.data else None


def upsert_user(telegram_user_id: int, chat_id: int, display_name: str):
    now = datetime.now(timezone.utc).isoformat()
    response = supabase.table("users").upsert(
        {
            "telegram_user_id": telegram_user_id,
            "chat_id": chat_id,
            "display_name": display_name,
            "last_active_at": now,
            "is_active": True,
        },
        on_conflict="telegram_user_id",
    ).execute()
    return response.data[0] if response.data else None


def get_user_by_telegram_id(telegram_user_id: int):
    response = supabase.table("users").select("*").eq("telegram_user_id", telegram_user_id).execute()
    return response.data[0] if response.data else None


def update_last_active(telegram_user_id: int):
    now = datetime.now(timezone.utc).isoformat()
    supabase.table("users").update(
        {"last_active_at": now}
    ).eq("telegram_user_id", telegram_user_id).execute()


def get_active_users():
    response = supabase.table("users").select("*").eq("is_active", True).execute()
    return response.data


def set_user_active(telegram_user_id: int, is_active: bool):
    supabase.table("users").update(
        {"is_active": is_active}
    ).eq("telegram_user_id", telegram_user_id).execute()


def update_reminder_time(telegram_user_id: int, time_str: str):
    supabase.table("users").update(
        {"reminder_time": time_str}
    ).eq("telegram_user_id", telegram_user_id).execute()


def update_nudge_time(telegram_user_id: int, time_str: str):
    supabase.table("users").update(
        {"nudge_time": time_str}
    ).eq("telegram_user_id", telegram_user_id).execute()


def get_user_items_today(user_id: str):
    now_ist = datetime.now(IST)
    today_start_ist = now_ist.replace(hour=0, minute=0, second=0, microsecond=0)
    today_start_utc = today_start_ist.astimezone(timezone.utc).isoformat()
    response = supabase.table("items").select("id").eq("user_id", user_id).gte("created_at", today_start_utc).execute()
    return response.data


def _delete_item_image(item_id: str):
    response = supabase.table("items").select("image_path").eq("id", item_id).execute()
    image_path = response.data[0]["image_path"] if response.data else None
    if not image_path:
        return
    try:
        supabase.storage.from_("images").remove([image_path])
    except Exception:
        return
    supabase.table("items").update({"image_path": None}).eq("id", item_id).execute()


def get_image_bytes(image_path: str):
    try:
        return supabase.storage.from_("images").download(image_path)
    except Exception:
        return None


def archive_item(item_id: str):
    # Images are kept in Storage for active items and only deleted once an item
    # is archived or acted on, rather than on a fixed 72h timer.
    supabase.table("items").update({"status": "archived"}).eq("id", item_id).execute()
    _delete_item_image(item_id)


def done_item(item_id: str):
    supabase.table("items").update({"status": "acted_on"}).eq("id", item_id).execute()
    _delete_item_image(item_id)


def remind_later(item_id: str, days: int = 3):

    resurface_at = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
    supabase.table("items").update({"resurface_after": resurface_at}).eq("id", item_id).execute()


def keep_item(item_id: str):

    resurface_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    supabase.table("items").update({
        "times_surfaced": 0,
        "resurface_after": resurface_at,
    }).eq("id", item_id).execute()


def set_remind_tonight(item_id: str, value: bool = True):
    supabase.table("items").update({"remind_tonight": value}).eq("id", item_id).execute()


def clear_remind_tonight(user_id: str):
    supabase.table("items").update({"remind_tonight": False}).eq("user_id", user_id).eq("remind_tonight", True).execute()


def get_remind_tonight_items(user_id: str) -> list:
    response = (
        supabase.table("items")
        .select("id, title, content_type, raw_content")
        .eq("user_id", user_id)
        .eq("remind_tonight", True)
        .execute()
    )
    return response.data


def get_categories_with_counts(user_id: str) -> list:
    cats = get_categories()
    response = (
        supabase.table("items")
        .select("category_id")
        .eq("user_id", user_id)
        .in_("status", ["fresh", "surfaced"])
        .execute()
    )
    counts = {}
    for item in response.data:
        cid = item.get("category_id")
        if cid:
            counts[cid] = counts.get(cid, 0) + 1
    result = []
    for cat in cats:
        result.append({
            "name": cat["name"],
            "description": cat["description"],
            "count": counts.get(cat["id"], 0),
        })
    result.sort(key=lambda x: -x["count"])
    return result


def search_items(user_id: str, keyword: str) -> list:
    now = datetime.now(timezone.utc)
    like_pattern = f"%{keyword}%"
    response = (
        supabase.table("items")
        .select("*, categories(name)")
        .eq("user_id", user_id)
        .in_("status", ["fresh", "surfaced"])
        .or_(f"title.ilike.{like_pattern},summary.ilike.{like_pattern},raw_content.ilike.{like_pattern}")
        .order("created_at", desc=True)
        .limit(10)
        .execute()
    )
    items = []
    for item in response.data:
        cat = item.pop("categories", None)
        item["category_name"] = cat["name"] if cat else None
        created_at = item.get("created_at")
        if created_at:
            from dateutil.parser import isoparse
            age = (now - isoparse(created_at)).total_seconds() / 86400
        else:
            age = 0
        item["age_days"] = age
        items.append(item)
    return items


def get_user_stats(user_id: str) -> dict:
    now = datetime.now(timezone.utc)
    week_ago = (now - timedelta(days=7)).isoformat()

    all_items = (
        supabase.table("items")
        .select("status, created_at, category_id")
        .eq("user_id", user_id)
        .execute()
    ).data

    total = len(all_items)
    active = sum(1 for i in all_items if i["status"] in ("fresh", "surfaced"))
    acted_on = sum(1 for i in all_items if i["status"] == "acted_on")
    archived = sum(1 for i in all_items if i["status"] == "archived")

    week_saved = sum(1 for i in all_items if i.get("created_at", "") >= week_ago)
    week_acted = sum(1 for i in all_items if i["status"] == "acted_on" and i.get("created_at", "") >= week_ago)
    week_archived = sum(1 for i in all_items if i["status"] == "archived" and i.get("created_at", "") >= week_ago)

    cat_counts = {}
    for i in all_items:
        cid = i.get("category_id")
        if cid:
            cat_counts[cid] = cat_counts.get(cid, 0) + 1

    cats = get_categories()
    cat_lookup = {c["id"]: c["name"] for c in cats}
    top_categories = sorted(cat_counts.items(), key=lambda x: -x[1])[:3]
    top_categories = [{"name": cat_lookup.get(cid, "Unknown"), "count": cnt} for cid, cnt in top_categories]

    return {
        "total": total,
        "active": active,
        "acted_on": acted_on,
        "archived": archived,
        "week_saved": week_saved,
        "week_acted": week_acted,
        "week_archived": week_archived,
        "top_categories": top_categories,
    }


def get_pending_items(user_id: str, days: int = None) -> list:
    now = datetime.now(timezone.utc)
    query = (
        supabase.table("items")
        .select("*, categories(name)")
        .eq("user_id", user_id)
        .in_("status", ["fresh", "surfaced"])
    )
    if days is not None:
        cutoff = (now - timedelta(days=days)).isoformat()
        query = query.gte("created_at", cutoff)
    response = query.execute()

    items = []
    for item in response.data:
        times_surfaced = item.get("times_surfaced") or 0
        goal = item.get("goal_alignment") or 1

        if times_surfaced >= 5 and goal < 3:
            continue

        resurface_after = item.get("resurface_after")
        if resurface_after:
            from dateutil.parser import isoparse
            if isoparse(resurface_after) > now:
                continue

        cat = item.pop("categories", None)
        item["category_name"] = cat["name"] if cat else None
        item["times_surfaced"] = times_surfaced
        item["goal_alignment"] = goal
        item["interest"] = item.get("interest") or 2
        items.append(item)

    return items



def update_item_embedding(item_id: str, embedding: list[float]):
    supabase.table("items").update({"embedding": embedding}).eq("id", item_id).execute()


def search_by_embedding(user_id: str, query_embedding: list[float], limit: int = 10, threshold: float = 0.75) -> list:
    response = supabase.rpc(
        "match_items",
        {
            "query_embedding": query_embedding,
            "match_threshold": threshold,
            "match_count": limit,
            "p_user_id": user_id,
        },
    ).execute()
    return response.data


def update_after_surface(item_id: str):


    response = supabase.table("items").select("times_surfaced, goal_alignment").eq("id", item_id).execute()
    if not response.data:
        return
    item = response.data[0]
    times_surfaced = (item.get("times_surfaced") or 0) + 1
    goal = item.get("goal_alignment") or 1
    now = datetime.now(timezone.utc)

    update_data = {
        "times_surfaced": times_surfaced,
        "last_surfaced_at": now.isoformat(),
        "status": "surfaced",
    }

    if goal < 3:
        if times_surfaced == 3:
            update_data["resurface_after"] = (now + timedelta(days=7)).isoformat()
        elif times_surfaced == 4:
            update_data["resurface_after"] = (now + timedelta(days=30)).isoformat()
        elif times_surfaced >= 5:
            update_data["status"] = "archived"

    supabase.table("items").update(update_data).eq("id", item_id).execute()
