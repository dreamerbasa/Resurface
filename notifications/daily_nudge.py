from datetime import datetime, timezone, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from db.queries import get_active_users, update_after_surface
from intelligence.scoring import get_daily_items


def _current_ist_time() -> str:
    now_ist = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
    m = now_ist.minute
    rounded_minute = 0 if m < 15 else 30 if m < 45 else 0
    if m >= 45:
        now_ist = now_ist.replace(hour=now_ist.hour + 1)
    return f"{now_ist.hour:02d}:{rounded_minute:02d}"


def _build_keyboard(item: dict) -> InlineKeyboardMarkup:
    item_id = item["id"]

    if item.get("is_escalation"):
        buttons = [
            [
                InlineKeyboardButton("Keep", callback_data=f"nudge_keep_{item_id}"),
                InlineKeyboardButton("Drop", callback_data=f"nudge_drop_{item_id}"),
            ]
        ]
    else:
        row = [
            InlineKeyboardButton("Archive", callback_data=f"nudge_archive_{item_id}"),
            InlineKeyboardButton("Remind later", callback_data=f"nudge_remind_{item_id}"),
            InlineKeyboardButton("Done", callback_data=f"nudge_done_{item_id}"),
        ]
        buttons = [row]
        if item.get("url"):
            buttons.append([InlineKeyboardButton("Open link", url=item["url"])])

    return InlineKeyboardMarkup(buttons)


def _format_item_text(item: dict) -> str:
    line = f"{item['emoji']} *{item['title']}* · {item['category_name']} · {item['age_days']:.0f}d ago"
    if item.get("is_escalation"):
        line += f"\n⚠️ You've seen this {item['times_surfaced']} times. Keep or drop?"
    return line


async def send_daily_nudge(context):
    current_window = _current_ist_time()
    users = get_active_users()

    for user in users:
        user_nudge = user.get("nudge_time", "08:30")
        if user_nudge != current_window:
            continue

        result = get_daily_items(user["id"])
        items = result.get("items", [])
        if not items:
            continue

        chat_id = user["chat_id"]

        if result.get("is_first_week"):
            header = "Getting started — here are your items to look at:"
        elif result.get("is_weekend_catchup"):
            header = (
                f"\U0001f4e6 Weekend catch-up — you have {result['total_pending']} unseen items\n\n"
                f"Top {len(items)} to review:"
            )
        else:
            header = f"☀️ Your {len(items)} item{'s' if len(items) != 1 else ''} for today"

        try:
            await context.bot.send_message(chat_id=chat_id, text=header)
        except Exception:
            continue

        for item in items:
            text = _format_item_text(item)
            keyboard = _build_keyboard(item)
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup=keyboard,
                    parse_mode="Markdown",
                )
                update_after_surface(item["id"])
            except Exception:
                pass
