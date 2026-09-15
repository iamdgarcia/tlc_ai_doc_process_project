#!/usr/bin/env python3
"""Evaluation runner for the Luma Spend agent.

Usage:
    cd /home/developer/proyectos/process_documents_api
    source venv/bin/activate
    python evals/run_eval.py [--experiment-prefix baseline]

Requires LANGSMITH_API_KEY in .env.
Second run with a different prefix creates a comparable experiment in LangSmith.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from sqlalchemy.orm import Session
from langsmith.evaluation import evaluate

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.chat import ChatService

from evaluators import (
    tool_selection_judge,
    conversational_quality,
    correct_arguments,
    task_completed,
    trajectory_efficiency,
    expected_facts,
    no_hallucinated_numbers,
)

DATASET_NAME = "luma-spend-agent-v1"


def predict(inputs: dict) -> dict:
    """Run the agent on a single question with a fresh, isolated DB session."""
    db: Session = SessionLocal()
    try:
        service = ChatService(session=db)
        return service.chat_for_eval(inputs["question"])
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Luma Spend agent evaluation.")
    parser.add_argument(
        "--experiment-prefix",
        default="baseline",
        help="LangSmith experiment prefix (change per run to compare)",
    )
    args = parser.parse_args()

    try:
        git_sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT
        ).decode().strip()
    except Exception:
        git_sha = "unknown"

    print(f"Running experiment '{args.experiment_prefix}' on dataset '{DATASET_NAME}'...")
    print(f"Model: {settings.openai_chat_model} | git: {git_sha}\n")

    results = evaluate(
        predict,
        data=DATASET_NAME,
        evaluators=[
            tool_selection_judge,       # LangSmith rubric: routing quality
            conversational_quality,     # LLM judge: tone, muletillas, style
            correct_arguments,          # deterministic: key arg values
            task_completed,             # deterministic: no step exhaustion
            trajectory_efficiency,      # deterministic: steps vs expected
            expected_facts,             # deterministic: facts in answer
            no_hallucinated_numbers,    # deterministic: number grounding
        ],
        experiment_prefix=args.experiment_prefix,
        metadata={
            "model": settings.openai_chat_model,
            "provider": "novita",
            "prompt_version": "1.0",
            "git_sha": git_sha,
            "dataset_version": "v1",
        },
        max_concurrency=1,
    )

    result_list = list(results)
    print(f"\nExperiment '{args.experiment_prefix}' complete — {len(result_list)} examples.")
    print("Open LangSmith to compare results: https://smith.langchain.com/")


if __name__ == "__main__":
    main()
