#!/usr/bin/env python3
"""Idempotent script to create or update the LangSmith evaluation dataset.

Usage:
    cd /home/developer/proyectos/process_documents_api
    source venv/bin/activate
    python evals/create_dataset.py

Requires LANGSMITH_API_KEY in .env.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from langsmith import Client

DATASET_NAME = "luma-spend-agent-v1"
SAMPLES_PATH = Path(__file__).parent / "dataset_samples.json"


def main() -> None:
    client = Client()
    samples: list[dict] = json.loads(SAMPLES_PATH.read_text())

    existing_datasets = {d.name: d for d in client.list_datasets()}
    if DATASET_NAME in existing_datasets:
        dataset = existing_datasets[DATASET_NAME]
        print(f"Dataset '{DATASET_NAME}' already exists (id={dataset.id})")
    else:
        dataset = client.create_dataset(
            DATASET_NAME,
            description="Evaluation dataset for Luma Spend ticket agent v1",
        )
        print(f"Created dataset '{DATASET_NAME}' (id={dataset.id})")

    existing_examples = {
        ex.inputs["question"]: ex
        for ex in client.list_examples(dataset_id=dataset.id)
    }

    created = 0
    updated = 0
    for sample in samples:
        question = sample["inputs"]["question"]
        if question in existing_examples:
            ex = existing_examples[question]
            client.update_example(
                ex.id,
                inputs=sample["inputs"],
                outputs=sample["outputs"],
                metadata=sample.get("metadata", {}),
            )
            updated += 1
        else:
            client.create_example(
                inputs=sample["inputs"],
                outputs=sample["outputs"],
                metadata=sample.get("metadata", {}),
                dataset_id=dataset.id,
            )
            created += 1

    print(f"Done: {created} created, {updated} updated, {len(samples)} total.")


if __name__ == "__main__":
    main()
