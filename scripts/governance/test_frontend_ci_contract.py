from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_desktop_frontend_ci_runs_tests_before_typecheck_and_build() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    install = workflow.index("- name: Install Vite desktop UI dependencies")
    test = workflow.index("- name: Test Vite desktop UI")
    typecheck = workflow.index("- name: Typecheck Vite desktop UI")
    build = workflow.index("- name: Build Vite desktop UI")

    assert install < test < typecheck < build
    test_block = workflow[test:typecheck]
    assert "run: npm run test" in test_block


def test_ci_collects_repository_governance_contracts() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert (
        "python -m pytest scripts/governance/test_repository_operational_contracts.py "
        "scripts/governance/test_frontend_ci_contract.py -q"
    ) in " ".join(workflow.split())
