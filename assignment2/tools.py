import os

from tavily import TavilyClient


def search(query: str) -> str:
    """Search the web using Tavily API."""
    try:
        client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
        response = client.search(query, max_results=3)
        results = []
        for r in response.get("results", []):
            results.append(f"- {r['title']}: {r['content']}")
        return "\n".join(results) if results else "No results found."
    except Exception as e:
        return f"Search error: {str(e)}"


def calculate(expression: str) -> str:
    """Evaluate a mathematical expression safely."""
    allowed_names = {
        "abs": abs, "round": round, "min": min, "max": max,
        "int": int, "float": float,
    }
    try:
        result = eval(expression, {"__builtins__": {}}, allowed_names)
        return str(result)
    except Exception as e:
        return f"Calculation error: {str(e)}"


TOOLS = {
    "Search": search,
    "Calculate": calculate,
}
