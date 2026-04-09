import os
import json
from typing import Annotated, List, TypedDict, Literal
from langgraph.graph import END, StateGraph
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain_chroma import Chroma
from termcolor import colored
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from config import get_embeddings, get_llm, DATA_FOLDER, DB_FOLDER, FILES


# Generic Retry Logic (Provider agnostic)
retry_logic = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(Exception)
)


def initialize_vector_dbs():
    embeddings = get_embeddings()
    retrievers = {}
    
    for key in FILES.keys():
        persist_dir = os.path.join(DB_FOLDER, key)

        if os.path.exists(persist_dir):
            vectorstore = Chroma(persist_directory=persist_dir, embedding_function=embeddings)
            retrievers[key] = vectorstore.as_retriever(search_kwargs={"k": 5})
        else:
            print(colored(f"❌ Error: Database for '{key}' not found!", "red"))
            print(colored(f"⚠️ Please run 'python build_rag.py' first.", "yellow"))
            continue
    
    return retrievers

RETRIEVERS = initialize_vector_dbs()


class AgentState(TypedDict):
    question: str
    documents: str
    generation: str
    search_count: int
    needs_rewrite: str


@retry_logic
def retrieve_node(state: AgentState):
    print(colored("--- 🔍 RETRIEVING ---", "blue"))
    question = state["question"]
    llm = get_llm()
    
    # --- [START] Improved Routing Logic ---
    options = list(FILES.keys()) + ["both", "none"]
    router_prompt = f"""You are a query router for a financial document retrieval system.
Your job is to classify the user's question into one of these categories: {', '.join(options)}.

Routing rules:
- "apple": The question is ONLY about Apple Inc. (e.g., iPhone, iPad, Mac, Apple Services, Tim Cook).
- "tesla": The question is ONLY about Tesla Inc. (e.g., electric vehicles, Elon Musk, Tesla Energy, Autopilot).
- "both": The question asks to COMPARE Apple and Tesla, or mentions BOTH companies, or asks about a general topic that requires data from both.
- "none": The question is unrelated to either Apple or Tesla financial data.

Output ONLY valid JSON with no extra text: {{"datasource": "..."}}

User Question: {question}"""
    
    try:
        response = llm.invoke(router_prompt)
        content = response.content.strip()
        # Handle cases where LLM might wrap JSON in backticks
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
            
        res_json = json.loads(content)
        target = res_json.get("datasource", "both")
    except Exception as e:
        print(colored(f"⚠️ Error parsing router output: {e}. Defaulting to 'both'.", "yellow"))
        target = "both"
    
    print(colored(f"🎯 Routing to: {target}", "cyan"))
    # --- [END] ---

    docs_content = ""
    targets_to_search = []
    if target == "both":
        targets_to_search = list(FILES.keys())
    elif target in FILES:
        targets_to_search = [target]
    
    for t in targets_to_search:
        if t in RETRIEVERS:
            docs = RETRIEVERS[t].invoke(question)
            source_name = t.capitalize()
            docs_content += f"\n\n[Source: {source_name}]\n" + "\n".join([d.page_content for d in docs])

    return {"documents": docs_content, "search_count": state["search_count"] + 1}

@retry_logic
def grade_documents_node(state: AgentState): 
    print(colored("--- ⚖️ GRADING ---", "yellow"))
    question = state["question"]
    documents = state["documents"]
    llm = get_llm()

    system_prompt = """You are a relevance grader for a financial document retrieval system.
Your task is to assess whether the retrieved document contains information that can help answer the user's question.

Grading criteria:
- Answer 'yes' if the document contains specific financial data, figures, or statements directly relevant to answering the question.
- Answer 'no' if the document is off-topic, contains data for the wrong company, wrong year, or lacks the specific information needed.
- If the question asks about future projections or information not found in 10-K filings, answer 'yes' ONLY if the document explicitly confirms that such information is NOT available (so the system can honestly say "I don't know").

CRITICAL: You must answer with ONLY one word: 'yes' or 'no'. Do not add any explanation."""
    
    msg = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"Retrieved document context: \n\n {documents} \n\n User question: {question}")
    ]
    
    response = llm.invoke(msg)
    content = response.content.strip().lower()
    
    grade = "yes" if "yes" in content else "no"
    print(f"   Relevance Grade: {grade}")
    return {"needs_rewrite": grade}

@retry_logic
def generate_node(state: AgentState):
    print(colored("--- ✍️ GENERATING ---", "green"))
    question = state["question"]
    documents = state["documents"]
    llm = get_llm() 
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are a senior financial analyst. Use ONLY the provided context to answer the question accurately.

STRICT RULES:
1. ANSWER IN ENGLISH: Always respond in English regardless of the question's language.
2. CITE SOURCES: Always cite the source at the end of your answer using the format [Source: Apple 10-K] or [Source: Tesla 10-K]. Use the [Source: ...] tags that appear in the context.
3. YEAR PRECISION: Financial data spans multiple years. Only report figures for the EXACT year asked about. Double-check column alignment.
4. EXACT FIGURES: When available, provide exact figures from the documents (e.g., "$391,035 million" or "$391.0 billion").
5. HONESTY: If the specific information is NOT found in the context, clearly state "I don't know" or "The provided documents do not contain this information." NEVER fabricate or estimate numbers.
6. COMPARISON: When comparing two companies, present data for each company separately, then provide the comparison conclusion.

Context:
{context}"""),
        ("human", "{question}"),
    ])
    
    chain = prompt | llm
    response = chain.invoke({"context": documents, "question": question})
    return {"generation": response.content}

@retry_logic
def rewrite_node(state: AgentState): 
    print(colored("--- 🔄 REWRITING QUERY ---", "red"))
    question = state["question"]
    llm = get_llm()
    
    msg = [
        SystemMessage(content="""You are a financial query optimization expert. Your job is to rewrite user questions to improve retrieval from financial 10-K filings.

Rewriting strategies:
1. Replace vague terms with precise financial terminology (e.g., "how much they spent on new tech" → "Research and Development expenses")
2. Add the specific year if missing (default to fiscal year 2024)
3. Use the exact line item names found in financial statements (e.g., "Total net sales", "Cost of sales", "Capital expenditures", "Gross margin")
4. If the question is in Chinese, translate it to English financial terminology
5. Specify the company name explicitly (Apple Inc. or Tesla Inc.)

Output ONLY the rewritten question text, nothing else."""),
        HumanMessage(content=f"The previous search for this question yielded irrelevant results. Please rewrite it:\n\n{question}")
    ]
    response = llm.invoke(msg)
    new_query = response.content.strip()
    print(f"   New Question: {new_query}")
    return {"question": new_query}

def build_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("retrieve", retrieve_node)
    workflow.add_node("grade_documents", grade_documents_node)
    workflow.add_node("generate", generate_node)
    workflow.add_node("rewrite", rewrite_node)

    workflow.set_entry_point("retrieve")
    workflow.add_edge("retrieve", "grade_documents")

    def decide_to_generate(state):
        if state["needs_rewrite"] == "yes":
            return "generate"
        else:
            if state["search_count"] > 2: 
                print("   (Max retries reached, generating anyway...)")
                return "generate"
            return "rewrite"

    workflow.add_conditional_edges(
        "grade_documents",
        decide_to_generate,
        {
            "generate": "generate",
            "rewrite": "rewrite"
        },
    )

    workflow.add_edge("rewrite", "retrieve")
    workflow.add_edge("generate", END)

    return workflow.compile()

def run_graph_agent(question: str):
    app = build_graph()
    inputs = {"question": question, "search_count": 0, "needs_rewrite": "no", "documents": "", "generation": ""}
    # Using stream to see progress if needed, but invoke is fine for simple return
    result = app.invoke(inputs)
    return result["generation"]

# --- Legacy ReAct Agent ---
def run_legacy_agent(question: str):
    print(colored("--- 🤖 RUNNING LEGACY AGENT (ReAct) ---", "magenta"))
    from langchain.agents import AgentExecutor, create_react_agent
    from langchain.tools.retriever import create_retriever_tool
    from langchain.tools.render import render_text_description

    tools = []
    for key, retriever in RETRIEVERS.items():
        tools.append(create_retriever_tool(
            retriever, 
            f"search_{key}_financials", 
            f"Searches {key.capitalize()}'s financial data."
        ))

    if not tools:
        return "System Error: No tools available."

    llm = get_llm()

    template = """You are a senior financial analyst with expertise in reading 10-K filings and financial statements. Answer the following questions as best you can using ONLY the retrieved data. You have access to the following tools:

{tools}

IMPORTANT RULES:
1. YEAR PRECISION: Financial tables contain columns for multiple years (2024, 2023, 2022). Pay extremely careful attention to which year the question asks about. Double-check the column headers before extracting any number. If the question asks for 2024 data, ONLY use the 2024 column.
2. ENGLISH ONLY: Your Final Answer MUST always be in English, even if the user's question is in Chinese or another language.
3. HONESTY: If you cannot find the exact figure in the retrieved documents, you MUST say "I don't know" or "The information is not available in the provided documents." NEVER guess or hallucinate numbers.
4. MULTI-SOURCE: If the question involves comparing Apple and Tesla, you MUST search BOTH company tools to gather data from each before answering.
5. CITATIONS: Always cite the source company in your Final Answer (e.g., [Source: Apple 10-K] or [Source: Tesla 10-K]).
6. PRECISION: Report exact figures from the financial statements when available (e.g., "$391,035 million" rather than "about $391 billion").

Use the following format:

Question: the input question you must answer
Thought: you should always think about what to do. Consider which company is being asked about and which tool to use.
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action. Use precise financial terminology (e.g., "Total net sales 2024", "Research and development expenses 2024").
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer. Let me verify the year and figures are correct.
Final Answer: the final answer to the original input question, in English, with source citations.

Begin!

Question: {input}
Thought: {agent_scratchpad}"""

    prompt = PromptTemplate.from_template(template)
    prompt = prompt.partial(
        tools=render_text_description(tools),
        tool_names=", ".join([t.name for t in tools])
    )

    agent = create_react_agent(llm, tools, prompt)
    agent_executor = AgentExecutor(
        agent=agent, 
        tools=tools, 
        verbose=True, 
        handle_parsing_errors=True,
        max_iterations=5
    )

    try:
        result = agent_executor.invoke({"input": question})
        return result["output"]
    except Exception as e:
        return f"Legacy Agent Error: {e}"