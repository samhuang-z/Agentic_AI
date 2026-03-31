# Browser Use Assignment — PagePilot + Claude

AI Browser Agent assignment using [PagePilot](https://github.com/jason79461385/PagePilot) with Claude Sonnet 4 (via litellm).

## Prerequisites

- Python 3.12+
- Google Chrome
- Anthropic API Key

## Setup

```bash
# 1. Clone PagePilot (sibling directory)
git clone https://github.com/jason79461385/PagePilot.git ../PagePilot

# 2. Create venv and install dependencies
cd ../PagePilot
uv venv --python 3.12
uv pip install -r requirements.txt
playwright install chromium

# 3. Set API key
export ANTHROPIC_API_KEY='your-key-here'
```

## Run

```bash
cd ../PagePilot
.venv/bin/python ../browser-use-assignment/src/agent_task.py
```

Results (screenshots, logs, cost summary) will be saved to `screenshots/`.

## Customization

Edit `agent_task.py` to change:
- `TASK` — the task definition (question + starting URL)
- `MODEL` — the LLM model (default: `anthropic/claude-sonnet-4-6`)
- `MAX_ITER` — maximum iterations (default: 10)
