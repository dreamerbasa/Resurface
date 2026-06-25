from pipeline.router import process_message

TEST_MESSAGES = [
    "startup idea: survivorship-bias-free constituent data for Indian quant funds",
    "try the new ramen place in koramangala, heard its amazing",
    "poem fragment: the city sleeps but I am wide awake, counting stars that forgot to shine",
]

if __name__ == "__main__":
    for i, msg in enumerate(TEST_MESSAGES, 1):
        print(f"\n{'='*60}")
        print(f"Test {i}: {msg[:50]}...")
        print("=" * 60)
        try:
            result = process_message(msg)
            print(f"  Category: {result['category_name']}")
            print(f"  Title:    {result['title']}")
            print(f"  Summary:  {result['summary']}")
            print(f"  Tags:     {', '.join(result['tags'])}")
        except Exception as e:
            print(f"  ERROR: {e}")

    print(f"\n{'='*60}")
    print("Check your Supabase dashboard — 3 items should be there.")
