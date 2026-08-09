"""Generate docs/AI_EMPLOYEE_CATALOG.md from agents/contract.json.

agents/contract.json is the single source of truth for the AI Employee roster.
This script renders the executive reference catalog from it so documentation and
implementation cannot drift: any change to the contract is a change to the
catalog by construction.

Run:  python scripts/generate_ai_employee_catalog.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "agents" / "contract.json"
OUT = ROOT / "docs" / "AI_EMPLOYEE_CATALOG.md"

_HEADER = """# AI Employee Catalog — the autonomous operating system

_Generated from `agents/contract.json` (the single source of truth) by
`scripts/generate_ai_employee_catalog.py`. Do not hand-edit — run the generator._

The platform is an autonomous operating cycle driven by **14 AI Employees**
(see `src/fointel/operate/graph.py::ROLE_ORDER`). Each employee is a thin,
framework-independent adapter over an existing business agent/service. The cycle
runs identically through the LangGraph executor (default) and the legacy
deterministic Orchestrator (`FOINTEL_ENGINE`). This catalog is the executive
reference for architects, technical leads, and engineers joining the project.

## How to read this catalog

Every employee spec is the same shape: **business objective · why it exists ·
trigger · inputs · outputs · responsibilities · tools · knowledge sources ·
authority boundary · escalation conditions · upstream/downstream dependencies ·
logs/metrics · repository location · test coverage**. Everything is grounded in
the implementation — capabilities here exist in `src/`, nothing is invented.

## The cycle

```
"""

_FOOTER = """```
scheduler -> engineering -> discovery -> entity -> duplicate -> enrichment
  -> validation -> classification -> governance -> release -> embedding
  -> freshness -> monitoring -> logging
```

## Employees

"""


def _render_one(name: str, s: dict) -> str:
    deps = s.get("dependencies", {})
    up = ", ".join(deps.get("upstream_employees") or ["(none)"])
    down = ", ".join(deps.get("downstream_employees") or ["(none)"])
    return (
        f"### {s.get('name', name)}\n\n"
        f"**Business objective.** {s.get('business_purpose', '')}\n\n"
        f"**Why it exists.** Mission: {s.get('name', '')} — see the in-code "
        f"EmployeeContract in `src/fointel/operate/adapters.py`.\n\n"
        f"**Trigger.** Position {s.get('execution_order')} of 14 in the cycle "
        f"(`ROLE_ORDER`); the cycle runs on schedule via "
        f"`.github/workflows/operating-cycle.yml`.\n\n"
        f"**Inputs.** {_bullet(s.get('inputs'))}\n\n"
        f"**Outputs.** {_bullet(s.get('outputs'))}\n\n"
        f"**Responsibilities.** {_bullet(s.get('responsibilities'))}\n\n"
        f"**Tools.** {_bullet(s.get('tools_used'))}\n\n"
        f"**Knowledge sources.** {_bullet(s.get('knowledge_sources'))}\n\n"
        f"**Authority boundary.** {s.get('authority_boundary', '')}\n\n"
        f"**Autonomous actions.** {', '.join(s.get('autonomous_actions') or [])}\n\n"
        f"**Escalation conditions.** {_bullet(s.get('escalation_rules'))}\n\n"
        f"**Upstream dependencies.** {up}  ·  **Downstream dependencies.** {down}\n\n"
        f"**Consumes / Produces.** consumes: {_inline(s.get('consumes'))} · "
        f"produces: {_inline(s.get('produces'))}\n\n"
        f"**Logs produced.** {_bullet(s.get('structured_logs_generated'))}\n\n"
        f"**Metrics produced.** {_bullet(s.get('metrics_produced'))}\n\n"
        f"**Checkpoint support.** {s.get('checkpoint_support')}  ·  "
        f"**Review gate.** {s.get('human_approval_conditions')}\n\n"
        f"**Framework independence.** {s.get('framework_independence')}\n\n"
        f"**Repository location.** {_inline(s.get('related_repository_files'))}\n\n"
        f"**Unit tests.** {_bullet(s.get('unit_tests'))}\n\n"
        f"**Integration tests.** {_bullet(s.get('integration_tests'))}\n\n---\n"
    )


def _bullet(items) -> str:
    if not items:
        return "_(none)_"
    return "\n".join(f"- {i}" for i in items)


def _inline(items) -> str:
    if not items:
        return "_(none)_"
    return ", ".join(items)


def main() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    lines = [_HEADER, _render_cycle(contract), _FOOTER]
    for name in contract["cycle"]:
        lines.append(_render_one(name, contract["agents"][name]))
    OUT.write_text("".join(lines), encoding="utf-8")
    print(f"wrote {OUT} ({len(contract['agents'])} employees)")


def _render_cycle(contract: dict) -> str:
    return "\n".join(f"{i}: {name}"
                     for i, name in enumerate(contract["cycle"]))


if __name__ == "__main__":
    main()