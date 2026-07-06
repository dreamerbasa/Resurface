from datetime import datetime, timezone, timedelta

from db.queries import get_active_users, get_user_items_today

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

        try:
            await context.bot.send_message(chat_id=chat_id, text=msg)
            print(f"Sent reminder to {user['display_name']}: {count} items today")
        except Exception as e:
            print(f"ERROR sending reminder to {user.get('display_name')}: {type(e).__name__}: {e}")
