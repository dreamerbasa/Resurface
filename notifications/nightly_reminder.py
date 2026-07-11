import logging
from datetime import datetime, timezone, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from db.queries import get_active_users, get_user_items_today, get_remind_tonight_items, clear_remind_tonight, get_cleanup_candidates
from notifications.nudge_session import set_session, get_session
from notifications.daily_nudge import build_list_view, escape_html
from intelligence.scoring import _get_emoji, _extract_url

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))


def _current_ist_time() -> str:
    now_ist = datetime.now(IST)
    total_minutes = now_ist.hour * 60 + now_ist.minute
    snapped = (total_minutes // 30) * 30
    h, m = divmod(snapped, 60)
    return f"{h:02d}:{m:02d}"


async def send_nightly_reminder(context):
    logger.info(f"Reminder check running at {datetime.now(IST)} IST")
    current_window = _current_ist_time()
    users = get_active_users()
    logger.info(f"Active users found: {len(users)}")

    for user in users:
        user_reminder = user.get("reminder_time", "22:00")
        if len(user_reminder) > 5:
            user_reminder = user_reminder[:5]
        logger.info(f"User {user['display_name']}: reminder_time={user_reminder}, current_window={current_window}, match={user_reminder == current_window}")
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

        try:
            await context.bot.send_message(
                chat_id=chat_id, text=msg,
                parse_mode="HTML", disable_web_page_preview=True,
            )
            logger.info(f"Sent reminder to {user['display_name']}: {count} items today")
        except Exception as e:
            logger.error(f"ERROR sending reminder to {user.get('display_name')}: {type(e).__name__}: {e}")

        tonight_items = get_remind_tonight_items(user["id"])
        if tonight_items:
            try:
                await _send_remind_tonight(context, user, chat_id, tonight_items)
            except Exception as e:
                logger.error(f"ERROR sending remind-tonight to {user.get('display_name')}: {type(e).__name__}: {e}")

        # Sunday cleanup
        now_ist = datetime.now(IST)
        is_sunday = now_ist.weekday() == 6
        logger.info(f"REMINDER: Is Sunday={is_sunday} for {user['display_name']}")
        if is_sunday:
            candidates = get_cleanup_candidates(user["id"])
            logger.info(f"REMINDER: Sunday cleanup — {len(candidates)} candidates found for {user['display_name']}")
            if not candidates:
                logger.info(f"REMINDER: No cleanup candidates for {user['display_name']} (all items are < 21 days old, or interest/goal > 2)")
            else:
                try:
                    await _send_sunday_cleanup(context, user, chat_id)
                except Exception as e:
                    logger.error(f"ERROR sending cleanup to {user.get('display_name')}: {type(e).__name__}: {e}")


def _format_tonight_item(item: dict) -> dict:
    now = datetime.now(IST)
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    age_days = (now - created).total_seconds() / 86400
    cat = item.get("category") or {}
    return {
        "id": item["id"],
        "title": item.get("title") or "Untitled",
        "category_name": cat.get("name") if isinstance(cat, dict) else cat,
        "content_type": item.get("content_type"),
        "raw_content": item.get("raw_content"),
        "age_days": age_days,
        "times_surfaced": item.get("times_surfaced", 0),
        "interest": item.get("interest", 2),
        "goal_alignment": item.get("goal_alignment", 1),
        "is_escalation": False,
        "emoji": _get_emoji(item),
        "url": _extract_url(item.get("raw_content")) if item.get("content_type") == "url" else None,
        "summary": item.get("summary"),
        "extracted_text": item.get("extracted_text"),
        "image_path": item.get("image_path"),
        "go_deep": item.get("go_deep", False),
    }


async def _send_remind_tonight(context, user: dict, chat_id: int, tonight_items: list):
    formatted = [_format_tonight_item(i) for i in tonight_items]
    header = "📌 You wanted to revisit tonight"
    has_email = bool(user.get("email"))

    set_session(chat_id, formatted, header, has_email=has_email)
    session = get_session(chat_id)
    text, keyboard = build_list_view(session)

    await context.bot.send_message(
        chat_id=chat_id, text=text, reply_markup=keyboard,
        parse_mode="HTML", disable_web_page_preview=True,
    )
    clear_remind_tonight(user["id"])
    logger.info(f"Sent remind-tonight nudge to {user['display_name']}: {len(formatted)} items")


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
        "go_deep": item.get("go_deep", False),
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

    has_email = bool(user.get("email"))
    set_session(chat_id, formatted, header, has_email=has_email)

    buttons = []
    for idx, item in enumerate(formatted, 1):
        buttons.append(InlineKeyboardButton(f"  {idx}  ", callback_data=f"nudgelist_{item['id']}"))

    keyboard = InlineKeyboardMarkup([buttons]) if buttons else None

    await context.bot.send_message(
        chat_id=chat_id, text=text, reply_markup=keyboard,
        parse_mode="HTML", disable_web_page_preview=True,
    )
    logger.info(f"Sent Sunday cleanup to {user['display_name']}: {len(display)} candidates")
