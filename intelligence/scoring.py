import re
from datetime import datetime, timezone, timedelta

from config import supabase


_PRIORITY_MATRIX = {
    (3, 3): 9, (3, 2): 6, (3, 1): 4,
    (2, 3): 8, (2, 2): 5, (2, 1): 2,
    (1, 3): 7, (1, 2): 3, (1, 1): 1,
}

_MAX_DAYS_BY_WEIGHT = [
    (7, 2),   # weight 7-9: surface by day 2
    (5, 4),   # weight 5-6: surface by day 4
    (2, 6),   # weight 2-4: surface by day 6
    (1, 7),   # weight 1: surface by day 7
]


def _get_max_days(weight: int) -> int:
    if weight >= 7:
        return 2
    if weight >= 5:
        return 4
    if weight >= 2:
        return 6
    return 7


def _get_emoji(item: dict) -> str:
    if item.get("times_surfaced", 0) == 0:
        return "\U0001f195"
    if item.get("times_surfaced", 0) >= 3:
        return "⚠️"
    if item.get("goal_alignment") == 3:
        return "\U0001f3af"
    if item.get("interest") == 3:
        return "\U0001f525"
    return "\U0001f44d"


def get_priority_emoji(interest: int, goal_alignment: int, is_escalation: bool = False) -> str:
    if is_escalation:
        return "⚠️"
    if goal_alignment == 3:
        return "\U0001f3af"
    if interest == 3:
        return "\U0001f525"
    return "\U0001f44d"


def _parse_dt(val) -> datetime:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    from dateutil.parser import isoparse
    return isoparse(val)


def get_daily_items(user_id: str) -> dict:
    now = datetime.now(timezone.utc)
    is_weekend = now.weekday() >= 5

    user_resp = supabase.table("users").select("created_at").eq("id", user_id).execute()
    user_created = _parse_dt(user_resp.data[0]["created_at"]) if user_resp.data else now
    is_first_week = (now - user_created).total_seconds() < 7 * 86400

    response = (
        supabase.table("items")
        .select("*, categories(name)")
        .eq("user_id", user_id)
        .in_("status", ["fresh", "surfaced"])
        .execute()
    )

    all_items = response.data

    eligible = []
    for item in all_items:
        cat = item.pop("categories", None)
        item["category_name"] = cat["name"] if cat else None

        times_surfaced = item.get("times_surfaced") or 0
        goal = item.get("goal_alignment") or 1
        item["times_surfaced"] = times_surfaced
        item["goal_alignment"] = goal
        item["interest"] = item.get("interest") or 2

        if times_surfaced >= 5 and goal < 3:
            continue

        resurface_after = _parse_dt(item.get("resurface_after"))
        if resurface_after and resurface_after > now:
            continue

        eligible.append(item)

    total_pending = len(eligible)

    phase1_items = []
    phase2_items = []

    for item in eligible:
        created_at = _parse_dt(item.get("created_at"))
        item["_created_at"] = created_at
        item["age_days"] = round((now - created_at).total_seconds() / 86400, 1) if created_at else 0

        times_surfaced = item["times_surfaced"]
        last_surfaced = _parse_dt(item.get("last_surfaced_at"))

        if times_surfaced == 0:
            weight = _PRIORITY_MATRIX.get((item["interest"], item["goal_alignment"]), 1)
            max_days = _get_max_days(weight)
            item["_weight"] = weight
            item["_max_days"] = max_days
            item["_is_overdue"] = item["age_days"] >= max_days
            phase1_items.append(item)
        else:
            in_cooldown = (
                last_surfaced is not None
                and (now - last_surfaced).total_seconds() < 3 * 86400
                and times_surfaced < 3
            )
            if not in_cooldown:
                item["_weight"] = _PRIORITY_MATRIX.get((item["interest"], item["goal_alignment"]), 1)
                phase2_items.append(item)

    if is_weekend and len(phase1_items) > 3:
        phase1_items.sort(key=lambda x: x["_weight"], reverse=True)
        selected = []
        for item in phase1_items[:5]:
            selected.append(_format_item(item, slot_type="catchup", phase=1))
        return {
            "items": selected,
            "total_pending": total_pending,
            "phase1_count": len(phase1_items),
            "phase2_count": len(phase2_items),
            "is_weekend_catchup": True,
            "is_first_week": is_first_week,
        }

    phase1_items.sort(key=lambda x: (not x["_is_overdue"], x["_created_at"] or now))
    phase2_items.sort(key=lambda x: x["_weight"], reverse=True)

    selected = []
    selected_ids = set()

    # SLOT 1: New item (Phase 1)
    slot1 = None
    if phase1_items:
        slot1 = phase1_items[0]
        selected.append(_format_item(slot1, slot_type="new", phase=1))
        selected_ids.add(slot1["id"])
    elif phase2_items:
        slot1 = phase2_items[0]
        selected.append(_format_item(slot1, slot_type="priority", phase=2))
        selected_ids.add(slot1["id"])

    # SLOT 2: Scored item (Phase 2)
    slot2 = None
    for item in phase2_items:
        if item["id"] not in selected_ids:
            slot2 = item
            selected.append(_format_item(slot2, slot_type="priority", phase=2))
            selected_ids.add(slot2["id"])
            break
    if slot2 is None:
        for item in phase1_items:
            if item["id"] not in selected_ids:
                slot2 = item
                selected.append(_format_item(slot2, slot_type="new", phase=1))
                selected_ids.add(slot2["id"])
                break

    # SLOT 3: Flexible (overdue or treat)
    overdue_remaining = [i for i in phase1_items if i["_is_overdue"] and i["id"] not in selected_ids]
    if overdue_remaining:
        slot3 = overdue_remaining[0]
        selected.append(_format_item(slot3, slot_type="overdue", phase=1))
        selected_ids.add(slot3["id"])
    else:
        all_remaining = [i for i in eligible if i["id"] not in selected_ids]
        all_remaining.sort(key=lambda x: x.get("interest", 0), reverse=True)
        for item in all_remaining:
            if item.get("interest", 0) >= 2:
                selected.append(_format_item(item, slot_type="treat", phase=1 if item.get("times_surfaced", 0) == 0 else 2))
                selected_ids.add(item["id"])
                break

    return {
        "items": selected[:3],
        "total_pending": total_pending,
        "phase1_count": len(phase1_items),
        "phase2_count": len(phase2_items),
        "is_weekend_catchup": False,
        "is_first_week": is_first_week,
    }


def _extract_url(text):
    if not text:
        return None
    match = re.search(r'https?://\S+', text)
    return match.group(0) if match else None


def _format_item(item: dict, slot_type: str, phase: int) -> dict:
    return {
        "id": item["id"],
        "title": item.get("title"),
        "summary": item.get("summary"),
        "category_name": item.get("category_name"),
        "interest": item.get("interest"),
        "goal_alignment": item.get("goal_alignment"),
        "age_days": item.get("age_days", 0),
        "times_surfaced": item.get("times_surfaced", 0),
        "score": item.get("_weight"),
        "phase": phase,
        "slot_type": slot_type,
        "is_escalation": item.get("times_surfaced", 0) >= 3,
        "emoji": _get_emoji(item),
        "url": _extract_url(item.get("raw_content")) if item.get("content_type") == "url" else None,
        "content_type": item.get("content_type"),
        "raw_content": item.get("raw_content"),
        "extracted_text": item.get("extracted_text"),
        "image_path": item.get("image_path"),
    }


def get_daily_items_debug(user_id: str) -> dict:
    now = datetime.now(timezone.utc)

    response = (
        supabase.table("items")
        .select("*, categories(name)")
        .eq("user_id", user_id)
        .in_("status", ["fresh", "surfaced"])
        .execute()
    )

    all_items = response.data
    debug_items = []

    for item in all_items:
        cat = item.pop("categories", None)
        item["category_name"] = cat["name"] if cat else None

        times_surfaced = item.get("times_surfaced") or 0
        goal = item.get("goal_alignment") or 1
        interest = item.get("interest") or 2
        item["times_surfaced"] = times_surfaced
        item["goal_alignment"] = goal
        item["interest"] = interest

        created_at = _parse_dt(item.get("created_at"))
        age_days = round((now - created_at).total_seconds() / 86400, 1) if created_at else 0
        last_surfaced = _parse_dt(item.get("last_surfaced_at"))
        resurface_after = _parse_dt(item.get("resurface_after"))

        weight = _PRIORITY_MATRIX.get((interest, goal), 1)
        max_days = _get_max_days(weight)

        excluded = False
        exclude_reason = None

        if times_surfaced >= 5 and goal < 3:
            excluded = True
            exclude_reason = "decayed (surfaced 5+ times)"
        elif resurface_after and resurface_after > now:
            excluded = True
            exclude_reason = f"resurface_after not reached ({resurface_after.date()})"
        elif times_surfaced >= 1 and last_surfaced and (now - last_surfaced).total_seconds() < 3 * 86400 and times_surfaced < 3:
            excluded = True
            exclude_reason = "cooldown (surfaced < 3 days ago)"

        if times_surfaced == 0:
            phase = 1
        else:
            phase = 2

        debug_items.append({
            "title": item.get("title"),
            "category_name": item.get("category_name"),
            "interest": interest,
            "goal_alignment": goal,
            "age_days": age_days,
            "times_surfaced": times_surfaced,
            "weight": weight,
            "max_days": max_days,
            "is_overdue": age_days >= max_days and times_surfaced == 0,
            "phase": phase,
            "excluded": excluded,
            "exclude_reason": exclude_reason,
        })

    debug_items.sort(key=lambda x: (x["excluded"], -x["weight"]))

    return {
        "all_items": debug_items,
        "total": len(all_items),
    }
