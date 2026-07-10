from config import openai_client


def build_embedding_text(title: str = None, summary: str = None, tags: list = None) -> str:
    parts = []
    if title:
        parts.append(title)
    if summary:
        parts.append(summary)
    if tags:
        parts.append(" ".join(tags))
    return " ".join(parts).strip()


def generate_embedding(text: str) -> list[float] | None:
    if not text:
        return None
    if not openai_client:
        print("ERROR: OpenAI client not configured — cannot generate embedding")
        return None
    try:
        response = openai_client.embeddings.create(
            model="text-embedding-3-small",
            input=text,
        )
        return response.data[0].embedding
    except Exception as e:
        print(f"ERROR generating embedding: {type(e).__name__}: {e}")
        return None
