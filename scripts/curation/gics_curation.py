"""Propose curated GICS sub-industries for CVM companies with the Claude Message Batches API.

Development tool for #519/#520. Nothing here runs inside CVMAnalytics: the output is a
review spreadsheet that the owner approves before it becomes the curated dataset.

Authentication: the Anthropic SDK reads the active `ant auth login` profile (or
ANTHROPIC_API_KEY). Install the SDK in a separate environment; it is not an app dependency.

  submit  --registry cad_cia_aberta.csv --gics-workbook "GICS Map 2025.xlsx" --out DIR (--cd-cvm 9512,4170 | --all-active)
  collect --registry cad_cia_aberta.csv --out DIR [--batch-id ID]
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import unicodedata
from datetime import date
from pathlib import Path

import anthropic
import openpyxl

REPO = Path(__file__).resolve().parents[2]
STRUCTURE = REPO / "data" / "reference" / "gics_structure.csv"
MODEL = "claude-opus-5-5"
EFFORT = "medium"
MAX_SEARCHES = 3
# Batch prices (50% of list) in USD per million tokens for claude-opus-5-5, plus web search per call.
# cache_write is the 1-hour TTL rate (2x input) because the system prompt uses ttl="1h".
PRICE = {"input": 2.00, "cache_write": 4.00, "cache_read": 0.10, "output": 10.00, "search": 0.01}

# shortcut: hand-authored CVM sector -> plausible GICS sector codes; refine after the pilot review.
COHERENCE = {
    "Agricultura (Açúcar, Álcool e Cana)": {"30", "10", "15"},
    "Alimentos": {"30"},
    "Arrendamento Mercantil": {"40"},
    "Bancos": {"40"},
    "Bebidas e Fumo": {"30"},
    "Bolsas de Valores/Mercadorias e Futuros": {"40"},
    "Brinquedos e Lazer": {"25"},
    "Comunicação e Informática": {"45", "50"},
    "Comércio (Atacado e Varejo)": {"20", "25", "30", "35"},
    "Construção Civil, Mat. Constr. e Decoração": {"15", "20", "25", "60"},
    "Const. Civil, Mat. Const. e Decoração": {"15", "20", "25", "60"},
    "Crédito Imobiliário": {"40"},
    "Educação": {"25"},
    "Embalagens": {"15"},
    "Reflorestamento": {"15"},
    "Serviços médicos": {"35"},
    "Energia Elétrica": {"55"},
    "Extração Mineral": {"10", "15"},
    "Farmacêutico e Higiene": {"30", "35"},
    "Hospedagem e Turismo": {"25"},
    "Intermediação Financeira": {"40"},
    "Máquinas, Equipamentos, Veículos e Peças": {"20", "25"},
    "Máqs., Equip., Veíc. e Peças": {"20", "25"},
    "Metalurgia e Siderurgia": {"15", "20"},
    "Papel e Celulose": {"15"},
    "Petroquímicos e Borracha": {"15", "25"},
    "Petróleo e Gás": {"10"},
    "Saneamento, Serv. Água e Gás": {"55"},
    "Securitização de Recebíveis": {"40"},
    "Seguradoras e Corretoras": {"40"},
    "Serviços Médicos": {"35"},
    "Serviços Transporte e Logística": {"20"},
    "Telecomunicações": {"50"},
    "Têxtil e Vestuário": {"25"},
}
HOLDING_PREFIX = "Emp. Adm. Part. - "

SUBMIT_TOOL = {
    "name": "submit_classification",
    "description": "Record the final GICS classification for the company. Call exactly once, after research.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["sub_industry_code", "unclassified_reason", "confidence", "rationale", "evidence_url"],
        "properties": {
            "sub_industry_code": {"type": "string", "description": "8-digit GICS sub-industry code, or empty string when unclassifiable."},
            "unclassified_reason": {"type": "string", "description": "Why no sub-industry applies; empty string when classified."},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "rationale": {"type": "string", "description": "One sentence: principal activity and why it fits the sub-industry."},
            "evidence_url": {"type": "string", "description": "Best source URL used (company IR, CVM filing, regulator); empty if none."},
        },
    },
}

SYSTEM_RULES = """You classify Brazilian companies registered with the CVM into the GICS structure below, \
for CVMAnalytics, an analyst workbench. The result is a curated classification reviewed by a human; \
it is never presented as an official MSCI/S&P assignment.

Method (follow the GICS methodology):
- Classify by principal business activity, primarily the source of most revenue; use earnings and \
market perception only when revenues are split.
- Holding companies: classify by the dominant operating business they control; use Multi-Sector \
Holdings (40201030) only for diversified holdings with no dominant business.
- Single-asset concession companies (toll roads, transmission lines, plants) are classified by the \
activity of the concession.
- Securitization companies, financing vehicles and investment vehicles are classified in Financials \
by what they actually do.
- If the company is pre-operational, a shell, in liquidation with no activity, or you cannot \
determine its activity from evidence, return an empty code and explain in unclassified_reason. \
Never guess.
- The CVM sector label is a hint, not evidence; it is often coarse or outdated.
- Use web search to confirm the activity from primary sources (company investor relations, CVM \
filings, regulators). Keep searches focused.
- Confidence: high = primary source confirms a clear single activity; medium = activity clear but \
mixed segments or secondary sources; low = thin or conflicting evidence.

Finish by calling submit_classification exactly once.

GICS sub-industries (code | sector > industry group > industry > sub-industry: definition):
"""


def load_structure() -> dict[str, dict[str, str]]:
    with STRUCTURE.open(encoding="utf-8") as handle:
        return {row["sub_industry_code"]: row for row in csv.DictReader(handle)}


def load_definitions(workbook_path: str) -> dict[str, str]:
    sheet = openpyxl.load_workbook(workbook_path, data_only=True).worksheets[0]
    definitions = {}
    for row in sheet.iter_rows():
        for cell in row:
            if isinstance(cell.value, (int, float)) and len(str(int(cell.value))) == 8 and not cell.font.strike:
                text = sheet.cell(cell.row + 1, cell.column + 1).value
                definitions[str(int(cell.value))] = " ".join(str(text or "").split())
    return definitions


def load_registry(path: str) -> dict[str, dict[str, str]]:
    with open(path, encoding="latin1") as handle:
        rows = csv.DictReader(handle, delimiter=";")
        return {row["CD_CVM"]: row for row in rows if row["SIT"] == "ATIVO"}


def system_prompt(structure: dict[str, dict[str, str]], definitions: dict[str, str]) -> str:
    lines = [
        f"{code} | {r['sector']} > {r['industry_group']} > {r['industry']} > {r['sub_industry']}: {definitions.get(code, '')}"
        for code, r in structure.items()
    ]
    return SYSTEM_RULES + "\n".join(lines)


def company_prompt(row: dict[str, str]) -> str:
    fields = {
        "CVM code": row["CD_CVM"],
        "Legal name": row["DENOM_SOCIAL"],
        "Trade name": row["DENOM_COMERC"],
        "CNPJ": row["CNPJ_CIA"],
        "CVM sector label": row["SETOR_ATIV"],
        "Registration category": row["CATEG_REG"],
        "Issuer status": row["SIT_EMISSOR"],
        "Market": row["TP_MERC"],
        "Shareholder control": row["CONTROLE_ACIONARIO"],
    }
    return "Classify this company:\n" + "\n".join(f"- {k}: {v}" for k, v in fields.items() if v)


def coherence_flag(cvm_sector: str, code: str) -> str:
    if not code:
        return ""
    base = cvm_sector.removeprefix(HOLDING_PREFIX)
    if base == "Sem Setor Principal":
        return ""
    allowed = COHERENCE.get(unicodedata.normalize("NFC", base))
    if allowed is None:
        return f"no coherence rule for CVM sector '{base}'"
    if cvm_sector.startswith(HOLDING_PREFIX):
        allowed = allowed | {"40"}
    return "" if code[:2] in allowed else f"GICS sector {code[:2]} unusual for CVM sector '{base}'"


def submit(args: argparse.Namespace) -> None:
    registry = load_registry(args.registry)
    ids = sorted(registry) if args.all_active else [c.strip() for c in args.cd_cvm.split(",")]
    missing = [c for c in ids if c not in registry]
    if missing:
        raise SystemExit(f"Not active in the CVM registry: {missing}")
    system = system_prompt(load_structure(), load_definitions(args.gics_workbook))
    requests = [
        {
            "custom_id": f"cvm-{cd}",
            "params": {
                "model": MODEL,
                "max_tokens": 16000,
                "output_config": {"effort": args.effort},
                "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral", "ttl": "1h"}}],
                "tools": [
                    {"type": "web_search_20260209", "name": "web_search", "max_uses": args.max_searches},
                    SUBMIT_TOOL,
                ],
                "messages": [{"role": "user", "content": company_prompt(registry[cd])}],
            },
        }
        for cd in ids
    ]
    batch = anthropic.Anthropic().messages.batches.create(requests=requests)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "batch.json").write_text(json.dumps({"batch_id": batch.id, "cd_cvm": ids, "model": MODEL, "effort": args.effort}, indent=2))
    print(f"Submitted batch {batch.id} with {len(ids)} companies")


def usage_cost(usage) -> tuple[dict[str, int], float]:
    searches = getattr(getattr(usage, "server_tool_use", None), "web_search_requests", 0) or 0
    counts = {
        "input": usage.input_tokens or 0,
        "cache_write": usage.cache_creation_input_tokens or 0,
        "cache_read": usage.cache_read_input_tokens or 0,
        "output": usage.output_tokens or 0,
        "search": searches,
    }
    cost = sum(counts[k] * PRICE[k] / 1_000_000 for k in ("input", "cache_write", "cache_read", "output"))
    return counts, cost + searches * PRICE["search"]


def collect(args: argparse.Namespace) -> None:
    out = Path(args.out)
    meta = json.loads((out / "batch.json").read_text())
    batch_id = args.batch_id or meta["batch_id"]
    client = anthropic.Anthropic()
    batch = client.messages.batches.retrieve(batch_id)
    if batch.processing_status != "ended":
        raise SystemExit(f"Batch {batch_id} is {batch.processing_status}: {batch.request_counts}")
    registry, structure = load_registry(args.registry), load_structure()
    rows, failures, totals, total_cost = [], [], {}, 0.0
    for result in client.messages.batches.results(batch_id):
        cd = result.custom_id.removeprefix("cvm-")
        if result.result.type != "succeeded":
            failures.append({"cd_cvm": cd, "reason": result.result.type})
            continue
        message = result.result.message
        counts, cost = usage_cost(message.usage)
        total_cost += cost
        for key, value in counts.items():
            totals[key] = totals.get(key, 0) + value
        call = next((b for b in message.content if b.type == "tool_use" and b.name == "submit_classification"), None)
        if call is None:
            failures.append({"cd_cvm": cd, "reason": f"no classification (stop_reason={message.stop_reason})"})
            continue
        data, company = call.input, registry.get(cd, {})
        code = data["sub_industry_code"].strip()
        if code and code not in structure:
            failures.append({"cd_cvm": cd, "reason": f"invalid GICS code {code!r}"})
            continue
        path = structure.get(code, {})
        rows.append({
            "cd_cvm": cd,
            "company_name": company.get("DENOM_SOCIAL", ""),
            "cnpj": company.get("CNPJ_CIA", ""),
            "cvm_sector": company.get("SETOR_ATIV", ""),
            "sub_industry_code": code,
            "sub_industry": path.get("sub_industry", ""),
            "industry": path.get("industry", ""),
            "industry_group": path.get("industry_group", ""),
            "sector": path.get("sector", ""),
            "unclassified_reason": data["unclassified_reason"],
            "basis": "researched",
            "confidence": data["confidence"],
            "rationale": data["rationale"],
            "evidence_url": data["evidence_url"],
            "coherence_flag": coherence_flag(company.get("SETOR_ATIV", ""), code),
            "proposed_by": f"{MODEL} effort={meta.get('effort', EFFORT)} batch={batch_id}",
            "gics_version": path.get("gics_version", ""),
            "cost_usd": f"{cost:.4f}",
            "reviewer": "",
            "review_date": "",
            "owner_decision": "",
        })
    rows.sort(key=lambda r: int(r["cd_cvm"]))
    if rows:
        with (out / "review.csv").open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    report = {
        "batch_id": batch_id,
        "collected": str(date.today()),
        "companies": len(rows) + len(failures),
        "classified": sum(1 for r in rows if r["sub_industry_code"]),
        "unclassified": sum(1 for r in rows if not r["sub_industry_code"]),
        "coherence_flags": sum(1 for r in rows if r["coherence_flag"]),
        "failures": failures,
        "usage": totals,
        "cost_usd": round(total_cost, 4),
        "cost_per_company_usd": round(total_cost / max(len(rows) + len(failures), 1), 4),
    }
    (out / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps(report, indent=2, ensure_ascii=False))


def needs_review(row: dict[str, str], other: dict[str, str] | None) -> list[str]:
    reasons = []
    if other is None:
        reasons.append("missing in second pass")
    elif other["sub_industry_code"] != row["sub_industry_code"]:
        reasons.append("passes disagree")
    if row["confidence"] != "high" or (other and other["confidence"] != "high"):
        reasons.append("confidence below high")
    if row["coherence_flag"]:
        reasons.append("coherence flag")
    if not row["sub_industry_code"]:
        reasons.append("unclassified")
    return reasons


def compare(args: argparse.Namespace) -> None:
    def read(directory: str) -> dict[str, dict[str, str]]:
        with (Path(directory) / "review.csv").open(encoding="utf-8-sig") as handle:
            return {row["cd_cvm"]: row for row in csv.DictReader(handle)}

    first, second = read(args.a), read(args.b)
    rows = []
    for cd in sorted(set(first) | set(second), key=int):
        row = dict(first.get(cd) or second[cd])
        other = second.get(cd) if cd in first else None
        row["second_pass_code"] = other["sub_industry_code"] if other else ""
        row["second_pass_sub_industry"] = other["sub_industry"] if other else ""
        row["second_pass_rationale"] = other["rationale"] if other else ""
        row["review_reasons"] = "; ".join(needs_review(row, other))
        rows.append(row)
    with open(args.out, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    agree = sum(1 for r in rows if r["second_pass_code"] == r["sub_industry_code"])
    flagged = sum(1 for r in rows if r["review_reasons"])
    print(f"{len(rows)} companies, {agree} agree across passes, {flagged} need owner review -> {args.out}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p_submit = sub.add_parser("submit")
    p_submit.add_argument("--registry", required=True)
    p_submit.add_argument("--gics-workbook", required=True)
    p_submit.add_argument("--out", required=True)
    p_submit.add_argument("--effort", default=EFFORT, choices=["low", "medium", "high", "xhigh", "max"])
    p_submit.add_argument("--max-searches", type=int, default=MAX_SEARCHES)
    target = p_submit.add_mutually_exclusive_group(required=True)
    target.add_argument("--cd-cvm")
    target.add_argument("--all-active", action="store_true")
    p_collect = sub.add_parser("collect")
    p_collect.add_argument("--registry", required=True)
    p_collect.add_argument("--out", required=True)
    p_collect.add_argument("--batch-id")
    p_compare = sub.add_parser("compare", help="Merge two independent passes and flag rows for owner review")
    p_compare.add_argument("--a", required=True)
    p_compare.add_argument("--b", required=True)
    p_compare.add_argument("--out", required=True)
    args = parser.parse_args()
    {"submit": submit, "collect": collect, "compare": compare}[args.command](args)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
