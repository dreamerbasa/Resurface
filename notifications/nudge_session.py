_sessions: dict[int, dict] = {}


def set_session(chat_id: int, items: list, header: str) -> None:
    _sessions[chat_id] = {
        "items": {item["id"]: item for item in items},
        "order": [item["id"] for item in items],
        "header": header,
        "acted": {},
    }


def get_session(chat_id: int) -> dict | None:
    return _sessions.get(chat_id)
