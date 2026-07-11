from datetime import datetime, timezone, timedelta

import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from db.queries import get_active_users, get_user_items_today, get_remind_tonight_items, clear_remind_tonight, get_cleanup_candidates
from notifications.nudge_session import set_session, get_session
from notifications.daily_nudge import build_list_view, escape_html
from intelligence.scoring import _get_emoji, _extract_url

IST = timezone(timedelta(hours=5, minutes=30))


def _current_ist_time() -> str:
    now_ist = datetime.now(IST)
    total_minutes = now_ist.hour * 60 + now_ist.minute
    snapped = (total_minutes // 30) * 30
    h, m = divmod(snapped, 60)
    return f"{h:02d}:{m:02d}"


async def send_nightly_reminder(context):
    print(f"Reminder check running at {datetime.now(IST)} IST")
    current_window = _current_ist_time()
    users = get_active_users()
    print(f"Active users found: {len(users)}")

    for user in users:
        user_reminder = user.get("reminder_time", "22:00")
        if len(user_reminder) > 5:
            user_reminder = user_reminder[:5]
        print(f"User {user['display_name']}: reminder_time={user_reminder}, current_window={current_window}, match={user_reminder == current_window}")
        if user_reminder != current_window:
            continue

        items = get_user_items_today(user["id"])
        count = len(items)
        chat_id = user["chat_id"]

        if count > 0:
            msg = (
                f"You saved {count} item{'s' if count != 1 else ''} today. "
                "Anything else on your mind before the day ends?"
            )
        else:
            msg = (
                "Nothing saved today — quiet day or just forgot? "
                "Drop anything here before it slips away."
            )

        tonight_items = get_remind_tonight_items(user["id"])
        if tonight_items:
            msg += "\n\n📌 <b>Remind tonight:</b>"
            for item in tonight_items:
                title = item.get("title") or "Untitled"
                title = str(title).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                raw = item.get("raw_content") or ""
                url_match = re.search(r'https?://\S+', raw)
                if item.get("content_type") == "url" and url_match:
                    msg += f"\n• <a href='{url_match.group()}'>{title}</a>"
                else:
                    msg += f"\n• {title}"
            clear_remind_tonight(user["id"])

        try:
            await context.bot.send_message(
                chat_id=chat_id, text=msg,
                parse_mode="HTML", disable_web_page_preview=True,
            )
            print(f"Sent reminder to {user['display_name']}: {count} items today")
        except Exception as e:
            print(f"ERROR sending reminder to {user.get('display_name')}: {type(e).__name__}: {e}")

        # Sunday cleanup
        now_ist = datetime.now(IST)
        if now_ist.weekday() == 6:
            try:
                await _send_sunday_cleanup(context, user, chat_id)
            except Exception as e:
                print(f"ERROR sending cleanup to {user.get('display_name')}: {type(e).__name__}: {e}")


def _format_cleanup_item(item: dict) -> dict:
    return {
        "id": item["id"],
        "title": item.get("title") or "Untitled",
        "category_name": item.get("category_name"),
        "content_type": item.get("content_type"),
        "raw_content": item.get("raw_content"),
        "age_days": item.get("age_days", 0),
        "times_surfaced": item.get("times_surfaced", 0),
        "interest": item.get("interest", 2),
        "goal_alignment": item.get("goal_alignment", 1),
        "is_escalation": True,
        "emoji": _get_emoji(item),
        "url": _extract_url(item.get("raw_content")) if item.get("content_type") == "url" else None,
        "summary": item.get("summary"),
        "extracted_text": item.get("extracted_text"),
        "image_path": item.get("image_path"),
    }


async def _send_sunday_cleanup(context, user: dict, chat_id: int):
    candidates = get_cleanup_candidates(user["id"])
    if not candidates:
        return

    display = candidates[:5]
    formatted = [_format_cleanup_item(c) for c in display]

    header = f"🧹 Weekly cleanup — {len(candidates)} item{'s' if len(candidates) != 1 else ''} sitting for 3+ weeks"

    lines = [header, ""]
    for idx, item in enumerate(display, 1):
        title = escape_html(item.get("title") or "Untitled")
        age = item.get("age_days", 0)
        seen = item.get("times_surfaced", 0)
        lines.append(f"{idx}. {title} ({age:.0f}d ago, seen {seen}x)")

    text = "\n".join(lines)

    set_session(chat_id, formatted, header)

    buttons = []
    for idx, item in enumerate(formatted, 1):
        buttons.append(InlineKeyboardButton(f"  {idx}  ", callback_data=f"nudgelist_{item['id']}"))

    keyboard = InlineKeyboardMarkup([buttons]) if buttons else None

    await context.bot.send_message(
        chat_id=chat_id, text=text, reply_markup=keyboard,
        parse_mode="HTML", disable_web_page_preview=True,
    )
    print(f"Sent Sunday cleanup to {user['display_name']}: {len(display)} candidates")
