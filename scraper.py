import asyncio
import os
import re
from datetime import datetime, timezone
from urllib.parse import quote

from playwright.async_api import async_playwright
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError

# Usa la variable de entorno si existe; si no, localhost
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME = "pinterest_tattoos_db"
COLLECTION_NAME = "skull_tattoos"

client = MongoClient(MONGO_URI)
collection = client[DB_NAME][COLLECTION_NAME]

# Limpia la colección para que cada corrida deje exactamente 40 documentos
collection.delete_many({})
collection.create_index("image_url", unique=True)

STOPWORDS = {"tattoo", "tatuaje", "tatuajes", "para", "como", "esta", "design", "pin"}


async def scrape_skull_tattoos(search_query: str, max_results: int = 10):
    url = f"https://www.pinterest.com/search/pins/?q={quote(search_query)}"
    print(f"\nBuscando: '{search_query}'...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(3000)

            inserted_count = 0
            scroll_attempts = 0

            while inserted_count < max_results and scroll_attempts < 15:
                img_elements = await page.query_selector_all('img[src*="i.pinimg.com"]')

                for img in img_elements:
                    if inserted_count >= max_results:
                        break

                    src = await img.get_attribute("src")
                    alt_text = (await img.get_attribute("alt") or "").strip()

                    if not src or not re.search(r"/(236x|474x|736x)/", src):
                        continue

                    high_res_url = re.sub(r"/(236x|474x|736x)/", "/originals/", src)

                    title = alt_text if alt_text and alt_text.lower() != "pin" else f"Tatuaje: {search_query}"

                    words = re.findall(r"\w+", f"{alt_text} {search_query}".lower())
                    tags = {w for w in words if len(w) > 3 and w not in STOPWORDS}
                    tags.update({"calavera", "tattoo"})

                    doc = {
                        "title": title,
                        "category": "Skull Tattoos",
                        "search_term": search_query,
                        "image_url": high_res_url,
                        "thumbnail_url": src,
                        "tags": sorted(tags),
                        "source": "Pinterest",
                        "created_at": datetime.now(timezone.utc),
                    }

                    try:
                        collection.insert_one(doc)
                        inserted_count += 1
                        print(f"  [{inserted_count}/{max_results}] Guardado: {title[:40]}")
                    except DuplicateKeyError:
                        pass

                await page.evaluate("window.scrollBy(0, 1200)")
                await page.wait_for_timeout(2000)
                scroll_attempts += 1

            print(f"  Finalizada '{search_query}'. Nuevos registros: {inserted_count}")

        except Exception as e:
            print(f"  Error en el scraping: {e}")
        finally:
            await browser.close()


async def main():
    busquedas = [
        "tatuajes calaveras de azucar",
        "tatuajes calaveras realistas",
        "tatuaje calavera con rosas",
        "skull tattoo design blackwork",
    ]
    for b in busquedas:
        await scrape_skull_tattoos(b, max_results=10)

    print(f"\nTotal en la colección: {collection.count_documents({})}")


if __name__ == "__main__":
    asyncio.run(main())
