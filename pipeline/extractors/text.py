def extract(raw_content: str) -> dict:
    return {
        "content_type": "text",
        "raw_content": raw_content,
        "extracted_text": raw_content,
        "source_platform": "telegram",
    }
