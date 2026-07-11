REVIEW_PAGE_SIZE = 5

_sessions: dict[int, dict] = {}


def set_session(chat_id: int, items: list, header: str, has_email: bool = True, review_offset: int | None = None, search_keyword: str | None = None) -> None:
    _sessions[chat_id] = {
        "items": {item["id"]: item for item in items},
        "order": [item["id"] for item in items],
        "header": header,
        "acted": {},
        "has_email": has_email,
        "review_offset": review_offset,
        "search_keyword": search_keyword,
    }


def get_session(chat_id: int) -> dict | None:
    return _sessions.get(chat_id)
