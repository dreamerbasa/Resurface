from datetime import datetime, timezone

from config import supabase


def get_categories():
    response = supabase.table("categories").select("id, name, description").execute()
    return response.data


def insert_item(data: dict):
    response = supabase.table("items").insert(data).execute()
    return response.data[0]


def update_item_rating(item_id: str, field: str, value: int):
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
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    response = supabase.table("items").select("id").eq("user_id", user_id).gte("created_at", today_start).execute()
    return response.data


def update_after_surface(item_id: str):
    from datetime import timedelta

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

    supabase.table("items").update(update_data).eq("id", item_id).execute()
