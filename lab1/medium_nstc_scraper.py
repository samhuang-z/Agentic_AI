"""
Medium 難度 - NSTC 學術補助獎勵查詢爬蟲
目標：爬取國家科學及技術委員會學術補助獎勵紀錄
工具：Playwright + BeautifulSoup
挑戰：ASP.NET ViewState & PostBack form, session, hidden form fields
"""

import csv
import time
from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout
from bs4 import BeautifulSoup

URL = "https://wsts.nstc.gov.tw/STSWeb/Award/AwardMultiQuery.aspx"
SEARCH_YEAR_START = "113"
SEARCH_YEAR_END = "113"
OUTPUT_FILE = "nstc_awards.csv"
HEADLESS = True
MAX_PAGES = 5


def parse_table(page) -> list[dict]:
    """用 Playwright 直接解析結果表格"""
    html = page.content()
    soup = BeautifulSoup(html, "lxml")
    # NSTC 的結果表格 id 包含 grdResult
    table = soup.select_one("table[id*='grdResult']")
    if not table:
        tables = soup.find_all("table")
        table = max(tables, key=lambda t: len(t.find_all("tr")), default=None)
    if not table:
        return []

    rows = table.find_all("tr")
    if len(rows) < 2:
        return []

    # 表頭
    headers = [th.get_text(strip=True) for th in rows[0].find_all(["th", "td"])]
    if not any(headers):
        return []

    records = []
    for row in rows[1:]:
        cells = [td.get_text(strip=True) for td in row.find_all("td")]
        if len(cells) == len(headers) and any(cells):
            records.append(dict(zip(headers, cells)))

    return records


def scrape_awards():
    """使用 Playwright 自動化查詢 NSTC 獎勵"""
    all_records = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=HEADLESS,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="zh-TW",
        )
        page = context.new_page()
        page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page.set_default_timeout(30000)

        # Step 1: 載入首頁
        print(f"正在載入: {URL}")
        page.goto(URL, wait_until="networkidle", timeout=30000)
        time.sleep(1)

        # Step 2: 點擊第一個補助類別（國家科學及技術委員會補助研究計畫）
        print("點擊補助類別：國家科學及技術委員會補助研究計畫")
        page.click("#dtlItem_btnItem_0")
        page.wait_for_load_state("networkidle", timeout=15000)
        time.sleep(1)

        # Step 3: 設定年度範圍
        # 起始年度 select
        start_sel = page.query_selector("#wUctlAwardQueryPage_repQuery_ddlYRst_0")
        if start_sel:
            start_sel.select_option(value=SEARCH_YEAR_START)
            print(f"已設定起始年度: {SEARCH_YEAR_START}")

        # 結束年度 select
        end_sel = page.query_selector("#wUctlAwardQueryPage_repQuery_ddlYRend_0")
        if end_sel:
            end_sel.select_option(value=SEARCH_YEAR_END)
            print(f"已設定結束年度: {SEARCH_YEAR_END}")

        # 設定每頁顯示筆數為最大 (200)
        page_size = page.query_selector("#wUctlAwardQueryPage_ddlPageSize")
        if page_size:
            page_size.select_option(value="200")
            print("已設定每頁顯示: 200 筆")

        # Step 4: 點擊查詢按鈕
        print("點擊查詢...")
        page.click("#wUctlAwardQueryPage_btnQuery")
        try:
            page.wait_for_load_state("networkidle", timeout=30000)
        except PwTimeout:
            pass
        time.sleep(3)

        # Step 5: 解析第一頁結果
        records = parse_table(page)
        if records:
            all_records.extend(records)
            print(f"第 1 頁：抓到 {len(records)} 筆")
        else:
            print("未抓到資料，儲存 debug 檔案")
            with open("nstc_debug.html", "w", encoding="utf-8") as f:
                f.write(page.content())
            page.screenshot(path="nstc_debug.png")

        # Step 6: 處理分頁（用下一頁按鈕）
        for pg in range(2, MAX_PAGES + 1):
            next_btn = page.query_selector(
                "#wUctlAwardQueryPage_grdResult_btnNext"
            )
            if not next_btn or not next_btn.is_visible():
                print(f"無更多分頁（共 {pg - 1} 頁）")
                break

            try:
                next_btn.click()
                page.wait_for_load_state("networkidle", timeout=15000)
                time.sleep(2)

                records = parse_table(page)
                if records:
                    all_records.extend(records)
                    print(f"第 {pg} 頁：抓到 {len(records)} 筆")
                else:
                    break
            except Exception as e:
                print(f"分頁錯誤: {e}")
                break

        browser.close()

    return all_records


def save_csv(records, filename=OUTPUT_FILE):
    """儲存為 CSV"""
    if not records:
        print("無資料可儲存")
        return
    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=records[0].keys())
        writer.writeheader()
        writer.writerows(records)
    print(f"已儲存 {len(records)} 筆到 {filename}")


def main():
    print("=" * 60)
    print("NSTC 學術補助獎勵查詢爬蟲")
    print(f"搜尋條件 - 年度: {SEARCH_YEAR_START}~{SEARCH_YEAR_END}")
    print("=" * 60)

    records = scrape_awards()

    if records:
        print(f"\n共抓到 {len(records)} 筆獎勵紀錄")
        print("-" * 60)
        for i, r in enumerate(records[:5], 1):
            vals = list(r.values())
            print(f"{i}. {' | '.join(str(v)[:20] for v in vals[:4])}")
        if len(records) > 5:
            print(f"   ... 還有 {len(records) - 5} 筆")
        print("-" * 60)
        save_csv(records)
    else:
        print("\n未抓到資料，請查看 nstc_debug.html / nstc_debug.png")


if __name__ == "__main__":
    main()
