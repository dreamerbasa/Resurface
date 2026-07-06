import re
from datetime import datetime, timezone, timedelta

from db.queries import get_pending_items, get_pinned_message_id, set_pinned_message_id

IST = timezone(timedelta(hours=5, minutes=30))

_PRIORITY_MATRIX = {
    (3, 3): 9, (3, 2): 6, (3, 1): 4,
    (2, 3): 8, (2, 2): 5, (2, 1): 2,
    (1, 3): 7, (1, 2): 3, (1, 1): 1,
}


def _get_emoji(item: dict) -> str:
    times_surfaced = item.get("times_surfaced", 0)
    if times_surfaced == 0:
        return "\U0001f195"
    if times_surfaced >= 3:
        return "⚠️"
    if item.get("goal_alignment") == 3:
        return "\U0001f3af"
    if item.get("interest") == 3:
        return "\U0001f525"
    return "\U0001f44d"


def _escape(text) -> str:
    if text is None:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _build_pinned_text(items: list) -> str:
    now = datetime.now(timezone.utc)
    now_ist = datetime.now(IST)

    sorted_items = []
    for item in items:
        from dateutil.parser import isoparse
        created_at = isoparse(item["created_at"]) if isinstance(item.get("created_at"), str) else item.get("created_at", now)
        age_days = round((now - created_at).total_seconds() / 86400, 1)
        weight = _PRIORITY_MATRIX.get((item["interest"], item["goal_alignment"]), 1)
        sorted_items.append((item, age_days, weight))

    sorted_items.sort(key=lambda x: (-int(x[0]["times_surfaced"] == 0), -x[2]))

    total = len(sorted_items)
    show = sorted_items[:8]

    lines = [f"📋 Review Queue — {total} item{'s' if total != 1 else ''} pending", ""]
    for item, age_days, weight in show:
        emoji = _get_emoji(item)
        title = _escape(item.get("title") or "Untitled")
        ts = item.get("times_surfaced", 0)
        if ts >= 3:
            lines.append(f"{emoji} {title} ({age_days:.0f}d, seen {ts}x — decide?)")
        elif ts > 0:
            lines.append(f"{emoji} {title} ({age_days:.0f}d, seen {ts}x)")
        else:
            lines.append(f"{emoji} {title} ({age_days:.0f}d)")

    if total > 8:
        lines.append(f"\n... and {total - 8} more")

    lines.append(f"\n/review to act on these")
    lines.append(f"Updated: {now_ist.strftime('%H:%M')} IST")

    return "\n".join(lines)


async def update_pinned_queue(bot, user: dict):
    user_id = user["id"]
    chat_id = user["chat_id"]

    items = get_pending_items(user_id)
    if not items:
        text = "📋 Review Queue — all caught up! 🎉\n\n/review to check"
    else:
        text = _build_pinned_text(items)

    pinned_id = get_pinned_message_id(user_id)

    if pinned_id:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=pinned_id,
                text=text,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            return
        except Exception:
            pass

    try:
        msg = await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        set_pinned_message_id(user_id, msg.message_id)
        await bot.pin_chat_message(
            chat_id=chat_id,
            message_id=msg.message_id,
            disable_notification=True,
        )
    except Exception as e:
        print(f"ERROR pinning queue for {user.get('display_name')}: {e}")
