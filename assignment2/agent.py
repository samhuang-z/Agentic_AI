import os
import re

import anthropic

from tools import TOOLS

SYSTEM_PROMPT = """You are a ReAct (Reasoning + Acting) Agent. You solve complex questions by iterating through Thought, Action, and Observation steps.

IMPORTANT: Always respond in Traditional Chinese (繁體中文), including your Thought and Answer. Only the Action tool calls (Search queries, Calculate expressions) should remain in English for better search results.

Available Tools:
1. Search[query] - Search the web for current information
2. Calculate[expression] - Evaluate a math expression (Python syntax)

Rules:
- Always start with a Thought to plan your approach.
- Use Action to call a tool when you need information or computation.
- After receiving an Observation, reflect on whether it answered your question.
- If an Observation is unhelpful, empty, or irrelevant, reflect on why and try a different query or approach. Do NOT repeat the same failed query.
- Break complex problems into smaller, sequential steps.
- When you have enough information, provide a final Answer.

Format for tool use:
Thought: <your reasoning>
Action: ToolName[input]

Format for final answer:
Thought: <your reasoning>
Answer: <your final answer>

--- Example ---

Question: What is the population of France divided by the population of Belgium?

Thought: This question requires two pieces of data and a calculation. My plan:
1. Search for the current population of France
2. Search for the current population of Belgium
3. Divide the two numbers
Let me start with step 1.
Action: Search[France population 2025]

Observation: - France Population 2025: France has an estimated population of approximately 68.5 million people as of early 2025.

Thought: France has about 68.5 million people. Now I need Belgium's population for step 2.
Action: Search[Belgium population 2025]

Observation: - Belgium Population: Belgium has a population of approximately 11.7 million people as of 2025.

Thought: Now I have both numbers. France: 68.5 million, Belgium: 11.7 million. Let me calculate the ratio for step 3.
Action: Calculate[68.5 / 11.7]

Observation: 5.854700854700855

Thought: The calculation is complete. France's population divided by Belgium's population is approximately 5.85.
Answer: The population of France (approximately 68.5 million) divided by the population of Belgium (approximately 11.7 million) is about 5.85. This means France has roughly 5.85 times the population of Belgium.

--- End Example ---
"""


class ReActAgent:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.model = "claude-haiku-4-5-20251001"
        self.max_iterations = 5

    def execute(self, query: str) -> str:
        """Execute the ReAct loop for a given query."""
        print(f"\n{'='*60}")
        print(f"Question: {query}")
        print(f"{'='*60}")

        messages = [
            {"role": "user", "content": f"Question: {query}"},
        ]

        iteration = 0
        while iteration < self.max_iterations:
            iteration += 1
            print(f"\n--- Step {iteration} ---")

            # Call LLM with stop sequence to prevent hallucinated observations
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=messages,
                temperature=0.2,
                stop_sequences=["Observation:"],
            )

            assistant_msg = response.content[0].text.strip()
            print(assistant_msg)

            # Check if the response contains a final Answer
            if "Answer:" in assistant_msg:
                answer = assistant_msg.split("Answer:", 1)[-1].strip()
                messages.append({"role": "assistant", "content": assistant_msg})
                print(f"\n{'='*60}")
                print(f"Final Answer: {answer}")
                print(f"{'='*60}")
                return answer

            # Parse Action from the response
            action_match = re.search(r"Action:\s*(\w+)\[(.+?)\]", assistant_msg)
            if not action_match:
                # No action found — prompt the model to continue
                messages.append({"role": "assistant", "content": assistant_msg})
                messages.append(
                    {
                        "role": "user",
                        "content": "Please continue with an Action or provide a final Answer.",
                    }
                )
                continue

            tool_name = action_match.group(1)
            tool_input = action_match.group(2)

            # Execute the tool
            if tool_name in TOOLS:
                observation = TOOLS[tool_name](tool_input)
            else:
                observation = (
                    f"Error: Unknown tool '{tool_name}'. "
                    f"Available tools: {', '.join(TOOLS.keys())}"
                )

            print(f"\nObservation: {observation}")

            # Update conversation history
            messages.append({"role": "assistant", "content": assistant_msg})
            messages.append({"role": "user", "content": f"Observation: {observation}"})

        # Exhausted iterations — force a final answer
        print(f"\n[Agent reached max iterations ({self.max_iterations})]")
        messages.append(
            {
                "role": "user",
                "content": (
                    "You have reached the maximum number of steps. "
                    "Please provide your best Answer now based on what you have gathered."
                ),
            }
        )
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=messages,
            temperature=0.2,
        )
        final = response.content[0].text.strip()
        print(final)

        if "Answer:" in final:
            return final.split("Answer:", 1)[-1].strip()
        return final
