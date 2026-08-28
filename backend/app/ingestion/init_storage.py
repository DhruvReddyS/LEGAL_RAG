import asyncio
import json

from app.services.storage import ensure_storage_buckets


async def main() -> None:
    buckets = await ensure_storage_buckets()
    print(json.dumps({"status": "ready", "buckets": buckets}, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
