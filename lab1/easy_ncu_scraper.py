"""
Easy 難度 - NCU 官網新聞標題爬蟲
目標：爬取國立中央大學官網的最新消息標題
工具：requests + BeautifulSoup
"""

import csv
import requests
from bs4 import BeautifulSoup

URL = "https://www.ncu.edu.tw"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
}


def fetch_ncu_news():
    """抓取 NCU 官網首頁新聞與公告"""
    print(f"正在抓取: {URL}")
    resp = requests.get(URL, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "utf-8"

    soup = BeautifulSoup(resp.text, "lxml")
    news_items = []
    seen = set()

    # 中大新聞區（md_style2）
    news_section = soup.select_one(".md_style2")
    if news_section:
        for a in news_section.find_all("a", href=True):
            title = a.get_text(strip=True)
            href = a["href"]
            if title and len(title) > 3 and title not in seen:
                seen.add(title)
                news_items.append({"category": "中大新聞", "title": title, "url": href})

    # 校園公告區（md_style3）
    bulletin_section = soup.select_one(".md_style3")
    if bulletin_section:
        for a in bulletin_section.find_all("a", href=True):
            title = a.get_text(strip=True)
            href = a["href"]
            if title and len(title) > 3 and title not in seen and "更多" not in title:
                seen.add(title)
                news_items.append({"category": "校園公告", "title": title, "url": href})

    # 校園活動區（md_style8）
    events_section = soup.select_one(".md_style8")
    if events_section:
        for a in events_section.find_all("a", href=True):
            title = a.get_text(strip=True)
            href = a["href"]
            if title and len(title) > 3 and title not in seen:
                seen.add(title)
                news_items.append({"category": "校園活動", "title": title, "url": href})

    return news_items


def save_csv(news_items, filename="ncu_news.csv"):
    """儲存為 CSV 檔"""
    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["category", "title", "url"])
        writer.writeheader()
        writer.writerows(news_items)
    print(f"已儲存 {len(news_items)} 筆新聞到 {filename}")


def main():
    news = fetch_ncu_news()
    if not news:
        print("未抓到任何新聞，請檢查網站結構是否變更。")
        return

    print(f"\n共抓到 {len(news)} 則新聞：")
    print("-" * 60)
    for i, item in enumerate(news, 1):
        print(f"{i}. [{item['category']}] {item['title']}")
        print(f"   {item['url']}")
    print("-" * 60)

    save_csv(news)


if __name__ == "__main__":
    main()
