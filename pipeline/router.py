from datetime import datetime

from pipeline.extractors import text
from pipeline.classifier import classify
from db.queries import insert_item


def process_message(raw_content: str, content_type: str = "text") -> dict:
    if content_type == "text":
        extracted_data = text.extract(raw_content)
    else:
        raise ValueError(f"Unsupported content type: {content_type}")

    classification = classify(extracted_data["extracted_text"])

    item = {
        "content_type": extracted_data["content_type"],
        "raw_content": extracted_data["raw_content"],
        "extracted_text": extracted_data["extracted_text"],
        "category_id": classification["category_id"],
        "title": classification["title"],
        "summary": classification["summary"],
        "tags": classification["tags"],
        "status": "fresh",
        "processed_at": datetime.utcnow().isoformat(),
    }

    insert_item(item)

    return {
        "category_name": classification["category_name"],
        "title": classification["title"],
        "summary": classification["summary"],
        "tags": classification["tags"],
    }
