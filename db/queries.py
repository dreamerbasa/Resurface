from config import supabase


def get_categories():
    response = supabase.table("categories").select("id, name, description").execute()
    return response.data


def insert_item(data: dict):
    response = supabase.table("items").insert(data).execute()
    return response.data[0]
