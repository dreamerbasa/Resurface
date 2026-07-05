from intelligence.scoring import get_daily_items, get_daily_items_debug

user_id = "9de9bca1-8267-43bf-8160-0ec201d8f1c4"

print("=" * 70)
print("ALL ITEMS — PHASE ASSIGNMENT & ELIGIBILITY")
print("=" * 70)

debug = get_daily_items_debug(user_id)

print(f"\nTotal items: {debug['total']}")
print(f"\n{'TITLE':<28} {'PH':>3} {'W':>3} {'INT':>3} {'GOAL':>4} {'AGE':>5} {'SURF':>4} {'OVERDUE':<8} {'STATUS'}")
print("-" * 90)

for item in debug["all_items"]:
    title = (item["title"] or "untitled")[:26]
    overdue = "YES" if item["is_overdue"] else ""
    if item["excluded"]:
        status = f"EXCLUDED: {item['exclude_reason']}"
    else:
        status = "eligible"
    print(
        f"{title:<28} {item['phase']:>3} {item['weight']:>3} "
        f"{item['interest']:>3} {item['goal_alignment']:>4} "
        f"{item['age_days']:>5.1f} {item['times_surfaced']:>4} "
        f"{overdue:<8} {status}"
    )

print(f"\n{'=' * 70}")
print("DAILY NUDGE SELECTION")
print("=" * 70)

result = get_daily_items(user_id)

print(f"\nPool sizes: Phase 1 = {result['phase1_count']}, Phase 2 = {result['phase2_count']}")
print(f"Total pending: {result['total_pending']}")
print(f"Weekend catchup: {result['is_weekend_catchup']}")

print(f"\n{'─' * 50}")
for i, item in enumerate(result["items"], 1):
    slot = item["slot_type"]
    print(f"\nSlot {i} ({slot}): {item['emoji']} {item['title']}")
    print(f"   Category: {item['category_name']}")
    print(f"   Phase: {item['phase']} | Interest: {item['interest']} | Goal: {item['goal_alignment']}")
    print(f"   Age: {item['age_days']}d | Surfaced: {item['times_surfaced']}x | Score: {item['score']}")
    if item.get("is_escalation"):
        print(f"   ⚠️  ESCALATION CANDIDATE")
    if item.get("url"):
        print(f"   URL: {item['url'][:60]}")
