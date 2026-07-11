from db.queries import get_active_users
from notifications.weekly_digest import generate_digest_for_user


def main():
    users = get_active_users()
    if not users:
        print("No active users found")
        return

    user = users[0]
    user_id = user["id"]
    print(f"Generating digest for {user['display_name']}...\n")

    html = generate_digest_for_user(user_id)
    if not html:
        print("No HTML generated")
        return

    output_path = "test_digest_output.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Open {output_path} in your browser to preview the email")


if __name__ == "__main__":
    main()
