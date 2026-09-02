import asyncio
import os


async def main():
    print("Testing social post generation and publish...")
    try:
        from app.marketing import postiz_publish

        print("Postiz API:", postiz_publish.api_url())
        print("Postiz enabled:", postiz_publish.enabled())
        key = postiz_publish._key()
        print("Postiz key exists:", bool(key), "len:", len(key) if key else 0)

        # Test fetching integrations
        integrations = await postiz_publish.live_integrations_summary()
        print("Connected integrations:", integrations)

    except Exception as e:
        print("Error:", e)


if __name__ == "__main__":
    os.environ["PYTHONPATH"] = "."
    asyncio.run(main())
