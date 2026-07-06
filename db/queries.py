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
