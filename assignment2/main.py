from dotenv import load_dotenv

load_dotenv()

from agent import ReActAgent

TASKS = [
    {
        "id": 1,
        "name": "Planning & Quantitative Reasoning",
        "question": "What fraction of Japan's population is Taiwan's population as of 2025?",
    },
    {
        "id": 2,
        "name": "Technical Specificity",
        "question": "Compare the main display specs of iPhone 15 and Samsung S24.",
    },
    {
        "id": 3,
        "name": "Resilience & Reflection Test",
        "question": "Who is the CEO of the startup 'Morphic' AI search?",
    },
]


def run_tasks():
    """自動跑作業要求的 3 個 Task。"""
    agent = ReActAgent()
    for task in TASKS:
        print(f"\n{'#'*60}")
        print(f"# Task {task['id']}: {task['name']}")
        print(f"{'#'*60}")
        agent.execute(task["question"])


def interactive():
    """互動模式：自己輸入問題。"""
    agent = ReActAgent()
    print("ReAct Agent 互動模式（輸入 'exit' 離開）")
    while True:
        query = input("\n你的問題：").strip()
        if query.lower() in ("exit", "quit", "q"):
            break
        if query:
            agent.execute(query)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "-i":
        interactive()
    else:
        run_tasks()
