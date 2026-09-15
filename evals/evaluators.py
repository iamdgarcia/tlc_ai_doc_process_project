"""Evaluators for the Luma Spend agent evaluation pipeline.

Deterministic evaluators (fast, no LLM call):
  - correct_arguments   — key argument values match expected
  - task_completed      — agent finished without exhausting step limit
  - trajectory_efficiency — penalise unnecessary extra steps
  - expected_facts      — expected strings appear in answer
  - no_hallucinated_numbers — numbers in answer traceable to tool results

LLM-as-judge evaluators:
  - tool_selection_judge    — LangSmith rubric for tool selection accuracy
  - conversational_quality  — tone, muletillas, markdown abuse, conciseness
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

from openai import OpenAI


def _llm_client() -> OpenAI:
    return OpenAI(
        api_key=os.environ.get("OPENAI_API_KEY", ""),
        base_url=os.environ.get("BASE_URL"),
    )


def _chat_model() -> str:
    return os.environ.get("OPENAI_CHAT_MODEL", "nvidia/nemotron-3-nano-30b-a3b")


# ---------------------------------------------------------------------------
# LLM-as-judge: tool selection (LangSmith rubric)
# ---------------------------------------------------------------------------

_TOOL_SELECTION_PROMPT = """\
You are an expert data labeler. Your task is to grade the accuracy of an AI \
agent's tool selection during the resolution of a user query.

<Rubric>
Accurate tool selection:
- Uses the most appropriate tool for each step given the context
- Avoids unnecessary or redundant tool calls
- Uses tools in a logical order where dependencies exist
- Is semantically equivalent to the provided reference tool sequence, if present
</Rubric>

<Instructions>
1. Grade the following thread, evaluating whether the agent selected the right \
tools in the right order to resolve the user's query efficiently.
2. Evaluate both the choice of tools and whether any tools were unnecessary, \
missing, or could have been replaced with a more appropriate alternative.
</Instructions>

User query: {question}

Reference tool sequence (expected): {reference}

<trajectory>
{outputs}
</trajectory>

Respond ONLY with JSON: {{"score": float_0_to_1, "reasoning": "brief explanation"}}"""


def tool_selection_judge(run: Any, example: Any) -> dict:
    """LLM judge using the LangSmith tool-selection rubric."""
    outputs = run.outputs or {}
    tool_calls = outputs.get("tool_calls", [])
    question = (example.inputs or {}).get("question", "")
    reference = (example.outputs or {}).get("expected_tools", [])

    trajectory_text = json.dumps(
        [{"name": tc["name"], "arguments": tc.get("arguments", {})} for tc in tool_calls],
        ensure_ascii=False,
        indent=2,
    )
    reference_text = json.dumps(reference, ensure_ascii=False)

    prompt = _TOOL_SELECTION_PROMPT.format(
        question=question,
        reference=reference_text,
        outputs=trajectory_text,
    )

    try:
        client = _llm_client()
        response = client.chat.completions.create(
            model=_chat_model(),
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={"type": "json_object"},
        )
        result = json.loads(response.choices[0].message.content or "{}")
        return {
            "key": "tool_selection",
            "score": float(result.get("score", 0.5)),
            "comment": result.get("reasoning", ""),
        }
    except Exception as exc:
        return {"key": "tool_selection", "score": 0.5, "comment": f"Evaluator error: {exc}"}


# ---------------------------------------------------------------------------
# LLM-as-judge: conversational quality
# ---------------------------------------------------------------------------

_CONVERSATIONAL_PROMPT = """\
Evalúa esta respuesta del asistente de compras de Luma Spend.

RESPUESTA:
{answer}

Criterios (penaliza si hay problemas):
1. Tono natural, no robótico ni excesivamente formal.
2. Sin muletillas repetitivas: "Claro", "Por supuesto", "Perfecto", "¡Entendido!", "¡Claro!".
3. Sin markdown innecesario (**negrita**, ## cabeceras) en contexto conversacional.
4. Conciso y directo. No verboso.
5. Español correcto.

Responde SOLO con JSON: {{"score": float_0_to_1, "comment": "explicación breve"}}"""


def conversational_quality(run: Any, example: Any) -> dict:
    """LLM judge: tone, muletillas, markdown abuse, conciseness, Spanish."""
    answer = (run.outputs or {}).get("answer", "")
    if not answer.strip():
        return {"key": "conversational_quality", "score": 0.0, "comment": "Empty answer."}

    try:
        client = _llm_client()
        response = client.chat.completions.create(
            model=_chat_model(),
            messages=[{"role": "user", "content": _CONVERSATIONAL_PROMPT.format(answer=answer)}],
            temperature=0,
            response_format={"type": "json_object"},
        )
        result = json.loads(response.choices[0].message.content or "{}")
        return {
            "key": "conversational_quality",
            "score": float(result.get("score", 0.5)),
            "comment": result.get("comment", ""),
        }
    except Exception as exc:
        return {"key": "conversational_quality", "score": 0.5, "comment": f"Evaluator error: {exc}"}


# ---------------------------------------------------------------------------
# Deterministic evaluators
# ---------------------------------------------------------------------------

def correct_arguments(run: Any, example: Any) -> dict:
    """Check that key tool arguments match expected values (partial string match for names)."""
    expected_args: dict = (example.outputs or {}).get("expected_arguments", {})
    if not expected_args:
        return {"key": "correct_arguments", "score": 1.0, "comment": "No argument constraints."}

    tool_calls = (run.outputs or {}).get("tool_calls", [])
    matched = 0
    mismatches: list[str] = []

    for key, expected_val in expected_args.items():
        found = False
        for tc in tool_calls:
            args = tc.get("arguments", {})
            if key not in args:
                continue
            actual_val = args[key]
            if isinstance(expected_val, str) and isinstance(actual_val, str):
                if expected_val.lower() in actual_val.lower() or actual_val.lower() in expected_val.lower():
                    matched += 1
                    found = True
                    break
            elif actual_val == expected_val:
                matched += 1
                found = True
                break
            else:
                mismatches.append(f"{key}: expected={expected_val!r}, got={actual_val!r}")
                found = True
                break
        if not found:
            mismatches.append(f"{key}: not found in any tool call")

    score = matched / len(expected_args)
    return {
        "key": "correct_arguments",
        "score": score,
        "comment": "; ".join(mismatches) if mismatches else "All key arguments match.",
    }


def task_completed(run: Any, example: Any) -> dict:
    """Binary: did the agent finish without exhausting the step limit?"""
    completed = (run.outputs or {}).get("completed", False)
    return {
        "key": "task_completed",
        "score": 1.0 if completed else 0.0,
        "comment": "Agent completed the task." if completed else "Agent exhausted step limit.",
    }


def trajectory_efficiency(run: Any, example: Any) -> dict:
    """Penalise agents that use more LLM calls than necessary."""
    expected_tools = (example.outputs or {}).get("expected_tools", [])
    min_steps = max(1, len(expected_tools))
    actual_steps = (run.outputs or {}).get("steps", 0)

    if actual_steps <= min_steps + 1:
        score, comment = 1.0, f"Efficient: {actual_steps} step(s)."
    elif actual_steps <= min_steps + 3:
        score, comment = 0.5, f"Slightly inefficient: {actual_steps} steps (min ~{min_steps})."
    else:
        score, comment = 0.0, f"Very inefficient: {actual_steps} steps (min ~{min_steps})."

    return {"key": "trajectory_efficiency", "score": score, "comment": comment}


def expected_facts(run: Any, example: Any) -> dict:
    """Check that expected fact strings appear (case-insensitive) in the answer."""
    facts: list[str] = (example.outputs or {}).get("expected_facts", [])
    if not facts:
        return {"key": "expected_facts", "score": 1.0, "comment": "No fact constraints."}

    answer = ((run.outputs or {}).get("answer") or "").lower()
    found = [f for f in facts if f.lower() in answer]
    missing = [f for f in facts if f.lower() not in answer]
    score = len(found) / len(facts)
    return {
        "key": "expected_facts",
        "score": score,
        "comment": f"Found: {found}. Missing: {missing}.",
    }


def _to_float_set(strings: set[str]) -> set[float]:
    result = set()
    for s in strings:
        try:
            result.add(round(float(s), 2))
        except ValueError:
            pass
    return result


def no_hallucinated_numbers(run: Any, example: Any) -> dict:
    """Detect numeric values in the answer that don't appear in tool results."""
    outputs = run.outputs or {}
    answer = (outputs.get("answer") or "").replace(",", ".").lower()
    tool_calls: list[dict] = outputs.get("tool_calls", [])

    answer_strs = set(re.findall(r"\d+(?:\.\d+)?", answer))
    if not answer_strs:
        return {"key": "no_hallucinated_numbers", "score": 1.0, "comment": "No numbers in answer."}

    if not tool_calls:
        return {"key": "no_hallucinated_numbers", "score": 1.0, "comment": "No tool calls — cannot verify numbers."}

    tool_text = " ".join(
        str(tc.get("result", "")) for tc in tool_calls
    ).replace(",", ".").lower()
    tool_strs = set(re.findall(r"\d+(?:\.\d+)?", tool_text))

    # Normalise to float so "500.50" == "500.5"
    answer_nums = _to_float_set(answer_strs)
    tool_nums = _to_float_set(tool_strs)
    allowed_nums = _to_float_set(
        {"1", "2", "3", "5", "10", "12", "30", "180", "365", "3650",
         "2023", "2024", "2025", "2026"}
    )
    hallucinated = answer_nums - tool_nums - allowed_nums

    score = max(0.0, 1.0 - len(hallucinated) * 0.25)
    return {
        "key": "no_hallucinated_numbers",
        "score": score,
        "comment": (
            f"Possible hallucinated numbers: {sorted(hallucinated)}"
            if hallucinated
            else "All numbers traceable to tool results."
        ),
    }
