import asyncio

from app.platform.plugin_registry import check_catalog_drift, get_plugin_catalog


async def main():
    catalog = get_plugin_catalog()
    print("Catalog size:", len(catalog))

    drift = await check_catalog_drift()
    print("Drift checked:", drift)


if __name__ == "__main__":
    asyncio.run(main())
