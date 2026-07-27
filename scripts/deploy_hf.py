"""
Deploy the Micro-RAG to Hugging Face Spaces (free, persistent, public URL).

Requires an HF token with write access (create at https://huggingface.co/settings/tokens):

    HF_TOKEN=hf_xxx python scripts/deploy_hf.py

Creates/updates a Docker Space and uploads the minimal deployable set (Dockerfile,
requirements, package source, and the delivered dataset CSV). Prints the live URL.
Set LLM_API_KEY as a Space secret afterwards to enable LLM-generated answers; the
service serves grounded extractive answers without it.
"""

from __future__ import annotations

import os
import sys

SPACE_README = """---
title: Family Office Intelligence
emoji: 🏛️
colorFrom: indigo
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
short_description: A grounded Micro-RAG over verified family-office records.
---

# Family Office Intelligence — Micro-RAG

A grounded retrieval system over 50 independently-verified family-office records
(SEC filings, SEC Form ADV registration, firm websites). Hybrid retrieval
(vector + BM25 + metadata) with a code-enforced grounding/abstention control:
the system declines when the evidence is insufficient rather than guessing.

Built for the PolarityIQ Differentiator, Stage 1.
Source: https://github.com/Emanyahyadev/polarity-fo-intel
"""


def main() -> None:
    token = os.environ.get("HF_TOKEN")
    if not token:
        sys.exit("Set HF_TOKEN (https://huggingface.co/settings/tokens) and re-run.")
    from huggingface_hub import HfApi

    api = HfApi(token=token)
    user = api.whoami()["name"]
    space = os.environ.get("HF_SPACE_NAME", "family-office-intelligence")
    repo_id = f"{user}/{space}"

    api.create_repo(repo_id, repo_type="space", space_sdk="docker", exist_ok=True)
    api.upload_file(path_or_fileobj=SPACE_README.encode("utf-8"), path_in_repo="README.md",
                    repo_id=repo_id, repo_type="space")
    for f in ("Dockerfile", "requirements.txt", "pyproject.toml"):
        api.upload_file(path_or_fileobj=f, path_in_repo=f, repo_id=repo_id, repo_type="space")
    api.upload_folder(folder_path="src", path_in_repo="src", repo_id=repo_id, repo_type="space")
    api.upload_file(path_or_fileobj="data/final/family_offices.csv",
                    path_in_repo="data/final/family_offices.csv",
                    repo_id=repo_id, repo_type="space")

    print(f"Space:    https://huggingface.co/spaces/{repo_id}")
    print(f"Live URL: https://{user.lower()}-{space}.hf.space  (allow ~2-4 min to build)")


if __name__ == "__main__":
    main()
