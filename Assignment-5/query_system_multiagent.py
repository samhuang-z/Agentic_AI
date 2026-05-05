"""Assignment 5 multi-agent QA entry point.

Output contract (consumed by auto_test_a5.py):
{
  "answer": str,
  "safety_decision": "ALLOW" | "REJECT",
  "diagnosis": "SUCCESS" | "QUERY_ERROR" | "SCHEMA_MISMATCH" | "NO_DATA",
  "repair_attempted": bool,
  "repair_changed": bool,
  "explanation": str,
}

Flow (Hybrid: fixed front half, dynamic back half):
  Understand -> Security -> [REJECT?] -> Plan -> Execute -> Diagnose
                                                                |
                              SUCCESS / NO_DATA -----------> Explain
                              QUERY_ERROR / SCHEMA_MISMATCH ---> Repair (max 1 round)
                                                                -> Execute' -> Diagnose'
                                                                -> Explain
"""

from __future__ import annotations

from typing import Any

from agents.pipeline import build_pipeline


PIPELINE = build_pipeline()


def answer_question(question: str) -> dict[str, Any]:
    nlu = PIPELINE["nlu"]
    security_agent = PIPELINE["security"]
    planner = PIPELINE["planner"]
    executor = PIPELINE["executor"]
    diagnosis_agent = PIPELINE["diagnosis"]
    repair_agent = PIPELINE["repair"]
    explanation_agent = PIPELINE["explanation"]
    synthesize_answer = PIPELINE["synthesize_answer"]

    intent = nlu.run(question)

    # 1) Security gate — runs before any KG access.
    security = security_agent.run(question, intent)
    if security["decision"] == "REJECT":
        diagnosis = {"label": "QUERY_ERROR", "reason": security["reason"]}
        answer = "Request rejected by security policy."
        explanation = explanation_agent.run(
            question, intent, security, diagnosis, answer, False, sources=[]
        )
        return {
            "answer": answer,
            "safety_decision": "REJECT",
            "diagnosis": diagnosis["label"],
            "repair_attempted": False,
            "repair_changed": False,
            "explanation": explanation,
        }

    # 2) Plan + execute + diagnose.
    plan = planner.run(intent)
    execution = executor.run(plan)
    diagnosis = diagnosis_agent.run(execution)

    repair_attempted = False
    repair_changed = False

    # 3) Dynamic back half — single repair round on retrieval failures
    #    (NO_DATA also benefits because empty-result is the most common
    #     symptom of an over-narrow query).
    if diagnosis["label"] in {"QUERY_ERROR", "SCHEMA_MISMATCH", "NO_DATA"}:
        repair_attempted = True
        repaired_plan = repair_agent.run(diagnosis, plan, intent)
        repair_changed = (
            repaired_plan.get("primary_query") != plan.get("primary_query")
            or repaired_plan.get("broad_query") != plan.get("broad_query")
            or repaired_plan.get("strategy") != plan.get("strategy")
        )
        execution = executor.run(repaired_plan)
        diagnosis = diagnosis_agent.run(execution)

    # 4) Synthesize a grounded answer from the (possibly repaired) execution.
    if diagnosis["label"] == "SUCCESS":
        answer = synthesize_answer(intent, execution.get("rows") or [])
    elif diagnosis["label"] == "NO_DATA":
        answer = "No matching regulation evidence found in KG."
    else:
        answer = "Query could not be resolved after repair attempt."

    explanation = explanation_agent.run(
        question, intent, security, diagnosis, answer,
        repair_attempted, sources=execution.get("sources") or [],
    )

    return {
        "answer": answer,
        "safety_decision": "ALLOW",
        "diagnosis": diagnosis["label"],
        "repair_attempted": repair_attempted,
        "repair_changed": repair_changed,
        "explanation": explanation,
    }


def run_multiagent_qa(question: str) -> dict[str, Any]:
    return answer_question(question)


def run_qa(question: str) -> dict[str, Any]:
    return answer_question(question)


if __name__ == "__main__":
    while True:
        try:
            q = input("Question (type exit): ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q or q.lower() in {"exit", "quit"}:
            break
        print(answer_question(q))
