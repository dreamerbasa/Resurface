from config import supabase


def get_categories():
    response = supabase.table("categories").select("id, name, description").execute()
    return response.data


def insert_item(data: dict):
    response = supabase.table("items").insert(data).execute()
    return response.data[0]


def update_item_rating(item_id: str, field: str, value: int):
    supabase.table("items").update({field: value}).eq("id", item_id).execute()


def get_item(item_id: str):
    response = supabase.table("items").select("interest, goal_alignment").eq("id", item_id).execute()
    return response.data[0] if response.data else None
