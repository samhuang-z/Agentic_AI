import os
import json
from dotenv import load_dotenv
from anthropic import Anthropic

# 從 .env 檔載入環境變數（API 金鑰等）
load_dotenv()

# 初始化 Anthropic 客戶端，從環境變數讀取 API 金鑰
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = os.getenv("MODEL", "claude-sonnet-4-20250514")

# ── 模擬資料函式 ─────────────────────────────────────────────────────
# 使用固定的模擬資料，不從網路抓取即時數據，確保評分一致性

EXCHANGE_RATES = {
    "USD_TWD": "32.0",
    "JPY_TWD": "0.2",
    "EUR_USD": "1.2",
}

STOCK_PRICES = {
    "AAPL": "260.00",
    "TSLA": "430.00",
    "NVDA": "190.00",
}


def get_exchange_rate(currency_pair: str) -> str:
    """查詢匯率。若查無資料則回傳錯誤訊息。"""
    rate = EXCHANGE_RATES.get(currency_pair.upper())
    if rate:
        return json.dumps({"currency_pair": currency_pair.upper(), "rate": rate})
    return json.dumps({"error": "Data not found"})


def get_stock_price(symbol: str) -> str:
    """查詢股價。若查無資料則回傳錯誤訊息。"""
    price = STOCK_PRICES.get(symbol.upper())
    if price:
        return json.dumps({"symbol": symbol.upper(), "price": price})
    return json.dumps({"error": "Data not found"})


# ── 函式對照表（Function Map）────────────────────────────────────────
# 使用字典做工具分派，避免冗長的 if-else 判斷鏈

available_functions = {
    "get_exchange_rate": get_exchange_rate,
    "get_stock_price": get_stock_price,
}

# ── 工具定義（Tool Schemas）──────────────────────────────────────────
# 定義 LLM 可呼叫的工具，包含名稱、描述與參數格式
# additionalProperties: False 確保不接受額外參數

tools = [
    {
        "name": "get_exchange_rate",
        "description": "Get the exchange rate for a currency pair. "
        "Supported pairs: USD_TWD, JPY_TWD, EUR_USD.",
        "input_schema": {
            "type": "object",
            "properties": {
                "currency_pair": {
                    "type": "string",
                    "description": "The currency pair, e.g. USD_TWD, JPY_TWD, EUR_USD.",
                }
            },
            "required": ["currency_pair"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_stock_price",
        "description": "Get the stock price for a given ticker symbol. "
        "Supported symbols: AAPL, TSLA, NVDA.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "The stock ticker symbol, e.g. AAPL, TSLA, NVDA.",
                }
            },
            "required": ["symbol"],
            "additionalProperties": False,
        },
    },
]

# ── 系統提示詞 ───────────────────────────────────────────────────────
# 定義 Agent 的角色與行為準則

SYSTEM_PROMPT = (
    "You are a Financial Assistant. You help users with exchange rates and "
    "stock prices. Use the provided tools to look up data. Be concise and "
    "helpful. If data is not found, inform the user politely."
)

# ── Agent 主迴圈 ─────────────────────────────────────────────────────


def run_agent():
    # messages 列表保存完整對話歷史，實現跨輪次記憶（Context Window）
    messages = []
    print("Financial Assistant (type 'quit' to exit)")
    print("-" * 45)

    while True:
        user_input = input("\nYou: ").strip()
        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit"):
            print("Goodbye!")
            break

        # 將使用者輸入加入對話歷史
        messages.append({"role": "user", "content": user_input})

        # 內層迴圈：持續呼叫 LLM，直到不再需要工具呼叫為止
        while True:
            response = client.messages.create(
                model=MODEL,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                tools=tools,
                messages=messages,
            )

            # 將助理的完整回應加入對話歷史
            assistant_content = response.content
            messages.append({"role": "assistant", "content": assistant_content})

            # 檢查回應中是否包含工具呼叫（支援一次多個＝平行工具呼叫）
            tool_uses = [b for b in assistant_content if b.type == "tool_use"]

            if not tool_uses:
                # 沒有工具呼叫，直接輸出文字回應並結束內層迴圈
                for block in assistant_content:
                    if hasattr(block, "text"):
                        print(f"\nAssistant: {block.text}")
                break

            # 執行所有待處理的工具呼叫，收集結果
            tool_results = []
            for tool_use in tool_uses:
                fn_name = tool_use.name
                fn_args = tool_use.input

                # 印出除錯資訊，方便 demo 影片展示
                print(f"  [Tool Call] {fn_name}({fn_args})")

                # 透過函式對照表（Function Map）分派呼叫，取代 if-else
                fn = available_functions.get(fn_name)
                if fn:
                    result = fn(**fn_args)
                else:
                    result = json.dumps({"error": f"Unknown function: {fn_name}"})

                print(f"  [Result]    {result}")

                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": result,
                    }
                )

            # 將所有工具結果一次加入對話歷史，再進行下一輪 LLM 呼叫
            messages.append({"role": "user", "content": tool_results})


if __name__ == "__main__":
    run_agent()
