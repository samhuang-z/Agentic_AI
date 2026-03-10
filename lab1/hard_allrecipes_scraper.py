"""
Hard 難度 - Allrecipes 食譜爬蟲
目標：爬取 Allrecipes 的食譜資料（recipe, ingredients, ratings, nutrition）
工具：Playwright + BeautifulSoup + JSON-LD extraction
挑戰：JS-rendered + anti-bot + pagination
Bonus：JSON-LD structured data extraction
"""

import json
import time
from typing import Optional
from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout
from bs4 import BeautifulSoup

CATEGORY_URL = "https://www.allrecipes.com/recipes/17562/dinner/"
OUTPUT_FILE = "recipes.json"
MAX_RECIPES = 5
HEADLESS = True

# 備用食譜 URL（確保至少能抓到 5 個）
FALLBACK_URLS = [
    "https://www.allrecipes.com/recipe/228293/curry-stand-chicken-tikka-masala-sauce/",
    "https://www.allrecipes.com/recipe/8496144/apple-fritter-pancakes/",
    "https://www.allrecipes.com/recipe/246628/chicken-marbella/",
    "https://www.allrecipes.com/recipe/234410/no-bake-chocolate-oat-bars/",
    "https://www.allrecipes.com/recipe/232458/simple-macaroni-and-cheese/",
    "https://www.allrecipes.com/recipe/23600/worlds-best-lasagna/",
    "https://www.allrecipes.com/recipe/219173/best-ever-banana-bread/",
    "https://www.allrecipes.com/recipe/16354/easy-meatloaf/",
    "https://www.allrecipes.com/recipe/26317/chicken-pot-pie-ix/",
    "https://www.allrecipes.com/recipe/24002/easy-taco-soup/",
]


def extract_recipe_json_ld(html: str) -> Optional[dict]:
    """從 HTML 中提取 JSON-LD Recipe 結構化資料"""
    soup = BeautifulSoup(html, "lxml")
    scripts = soup.find_all("script", type="application/ld+json")

    for script in scripts:
        if not script.string:
            continue
        try:
            data = json.loads(script.string)
            # JSON-LD 可能是 list 或 dict
            items = data if isinstance(data, list) else [data]
            for item in items:
                if not isinstance(item, dict):
                    continue
                item_type = item.get("@type", "")
                is_recipe = (item_type == "Recipe") or (
                    isinstance(item_type, list) and "Recipe" in item_type
                )
                if is_recipe:
                    return item
                # 有時 Recipe 在 @graph 裡面
                if "@graph" in item:
                    for node in item["@graph"]:
                        node_type = node.get("@type", "")
                        is_r = (node_type == "Recipe") or (
                            isinstance(node_type, list) and "Recipe" in node_type
                        )
                        if is_r:
                            return node
        except json.JSONDecodeError:
            continue
    return None


def parse_recipe(json_ld: dict, url: str) -> dict:
    """將 JSON-LD 資料整理成結構化 dict"""
    # 取得作者
    authors = json_ld.get("author", [])
    if isinstance(authors, dict):
        authors = [authors]
    author_names = [a.get("name", "") for a in authors if isinstance(a, dict)]

    # 取得營養資訊
    nutrition_raw = json_ld.get("nutrition", {})
    nutrition = None
    if nutrition_raw and isinstance(nutrition_raw, dict):
        nutrition = {
            "calories": nutrition_raw.get("calories"),
            "carbohydrate": nutrition_raw.get("carbohydrateContent"),
            "protein": nutrition_raw.get("proteinContent"),
            "fat": nutrition_raw.get("fatContent"),
            "sodium": nutrition_raw.get("sodiumContent"),
            "fiber": nutrition_raw.get("fiberContent"),
            "sugar": nutrition_raw.get("sugarContent"),
            "cholesterol": nutrition_raw.get("cholesterolContent"),
        }

    # 取得步驟
    instructions_raw = json_ld.get("recipeInstructions", [])
    instructions = []
    for step in instructions_raw:
        if isinstance(step, dict) and step.get("@type") == "HowToStep":
            instructions.append(step.get("text", ""))
        elif isinstance(step, str):
            instructions.append(step)

    # 取得評分
    rating_raw = json_ld.get("aggregateRating", {})
    rating = None
    if rating_raw and isinstance(rating_raw, dict):
        rating = {
            "value": rating_raw.get("ratingValue"),
            "count": rating_raw.get("ratingCount"),
        }

    return {
        "name": json_ld.get("name"),
        "description": json_ld.get("description"),
        "author": author_names,
        "prep_time": json_ld.get("prepTime"),
        "cook_time": json_ld.get("cookTime"),
        "total_time": json_ld.get("totalTime"),
        "recipe_yield": json_ld.get("recipeYield"),
        "category": json_ld.get("recipeCategory"),
        "cuisine": json_ld.get("recipeCuisine"),
        "ingredients": json_ld.get("recipeIngredient", []),
        "instructions": instructions,
        "nutrition": nutrition,
        "rating": rating,
        "url": url,
    }


def collect_recipe_urls(page) -> list[str]:
    """從分類頁收集食譜 URL"""
    urls = []
    # Allrecipes 食譜連結格式: /recipe/數字/名稱/
    links = page.query_selector_all('a[href*="/recipe/"]')
    seen = set()
    for link in links:
        href = link.get_attribute("href") or ""
        # 過濾有效食譜 URL
        if "/recipe/" in href and href not in seen:
            if not href.startswith("http"):
                href = "https://www.allrecipes.com" + href
            seen.add(href)
            urls.append(href)
    return urls


def scrape_recipe(page, url: str) -> Optional[dict]:
    """爬取單一食譜頁面"""
    print(f"  正在爬取: {url}")
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)

        html = page.content()
        json_ld = extract_recipe_json_ld(html)

        if not json_ld:
            print(f"  ⚠ 未找到 JSON-LD Recipe 資料")
            return None

        recipe = parse_recipe(json_ld, url)
        print(f"  ✓ {recipe['name']}")
        return recipe

    except PwTimeout:
        print(f"  ⚠ 載入逾時: {url}")
        return None
    except Exception as e:
        print(f"  ⚠ 錯誤: {e}")
        return None


def main():
    print("=" * 60)
    print("Allrecipes 食譜爬蟲（JSON-LD extraction）")
    print(f"分類頁: {CATEGORY_URL}")
    print(f"目標數量: {MAX_RECIPES} 個食譜")
    print("=" * 60)

    recipes = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()

        # Step 1: 從分類頁收集食譜 URL
        print("\n[Step 1] 從分類頁收集食譜連結...")
        try:
            page.goto(CATEGORY_URL, wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)
            recipe_urls = collect_recipe_urls(page)
            print(f"  找到 {len(recipe_urls)} 個食譜連結")
        except Exception as e:
            print(f"  分類頁載入失敗: {e}")
            recipe_urls = []

        # 合併備用 URL（去重）
        seen = set(recipe_urls)
        for u in FALLBACK_URLS:
            if u not in seen:
                recipe_urls.append(u)
                seen.add(u)
        print(f"  共 {len(recipe_urls)} 個候選食譜 URL")

        # Step 2: 逐一爬取食譜，直到成功抓到 MAX_RECIPES 個
        print(f"\n[Step 2] 爬取食譜（目標 {MAX_RECIPES} 個）...")
        for url in recipe_urls:
            recipe = scrape_recipe(page, url)
            if recipe:
                recipes.append(recipe)
                if len(recipes) >= MAX_RECIPES:
                    break
            time.sleep(2)  # 禮貌性延遲

        browser.close()

    # Step 3: 儲存結果
    if recipes:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(recipes, f, ensure_ascii=False, indent=2)
        print(f"\n已儲存 {len(recipes)} 個食譜到 {OUTPUT_FILE}")

        print("\n" + "=" * 60)
        for i, r in enumerate(recipes, 1):
            print(f"\n[{i}] {r['name']}")
            print(f"    作者: {', '.join(r['author']) if r['author'] else 'N/A'}")
            print(f"    時間: {r.get('total_time', 'N/A')}")
            print(f"    食材數: {len(r.get('ingredients', []))}")
            print(f"    步驟數: {len(r.get('instructions', []))}")
            if r.get("rating"):
                print(f"    評分: {r['rating']['value']} ({r['rating']['count']} 評)")
            if r.get("nutrition"):
                print(f"    熱量: {r['nutrition'].get('calories', 'N/A')}")
    else:
        print("\n未成功爬取任何食譜")


if __name__ == "__main__":
    main()
