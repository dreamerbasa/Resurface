from datetime import datetime, timezone

from db.queries import get_active_users, get_user_items_today


def _current_ist_time() -> str:
    from datetime import timedelta
    now_ist = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
    m = now_ist.minute
    rounded_minute = 0 if m < 15 else 30 if m < 45 else 0
    if m >= 45:
        now_ist = now_ist.replace(hour=now_ist.hour + 1)
    return f"{now_ist.hour:02d}:{rounded_minute:02d}"


async def send_nightly_reminder(context):
    current_window = _current_ist_time()
    users = get_active_users()

    for user in users:
        user_reminder = user.get("reminder_time", "22:00")
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
            await context.bot.send_message(chat_id=chat_id, text=msg)
        except Exception:
            pass
