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


def main():
    agent = ReActAgent()

    for task in TASKS:
        print(f"\n{'#'*60}")
        print(f"# Task {task['id']}: {task['name']}")
        print(f"{'#'*60}")
        agent.execute(task["question"])


if __name__ == "__main__":
    main()
