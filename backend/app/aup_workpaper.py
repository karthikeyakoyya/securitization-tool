"""
aup_workpaper.py

Assembles a "Procedures & Results" work paper -- the kind of document an
analyst drafts to support an Agreed-Upon Procedures (AUP) engagement
(see the JD line: "assist with Agreed Upon Procedures Report issuance").

This module does NOT produce a signed AUP report. A signed AUP report
(e.g. an "Independent Accountant's Report on Applying Agreed-Upon
Procedures" under AICPA AT-C 215 / IAASB ISRS 4400) is issued by an
accounting firm to specified parties and requires actual engagement
authority this project does not have and should not simulate. What this
module produces is the tier below that: a structured procedures-and-
results memo -- the real work product an analyst assembles from actual
recomputation, which a reviewer/partner would then use to draft the
signed report. That distinction is deliberate and worth stating in an
interview if asked what this is and is not.

Every procedure and result in the output is pulled directly from the
extractor, scorer, and cash flow engine already in this repo -- nothing
here is hand-written prose describing fictional findings.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .extraction import HeuristicExtractor, score_field_level_accuracy
from .cashflow_engine import TrancheInput, WaterfallAssumptions, run_sequential_waterfall, build_stratification_table

RAW_DIR = Path(__file__).resolve().parent.parent / "sample_data" / "raw"
GT_DIR = Path(__file__).resolve().parent.parent / "sample_data" / "ground_truth"

CONCENTRATION_HIGH = 20.0
CONCENTRATION_MED = 10.0


@dataclass
class ProcedureResult:
    procedure: str
    result_summary: str
    exceptions: list[str] = field(default_factory=list)


@dataclass
class DealWorkpaper:
    deal_label: str
    source_document: str
    field_level_accuracy_pct: float
    fields_scored: int
    fields_correct: int
    procedures: list[ProcedureResult] = field(default_factory=list)


def _document_abstraction_procedure(raw_name: str, gt_name: str, deal_label: str) -> tuple[DealWorkpaper, dict]:
    raw = (RAW_DIR / raw_name).read_text()
    gt = json.loads((GT_DIR / gt_name).read_text())
    deal = HeuristicExtractor().extract(raw, source_document=raw_name)
    acc = score_field_level_accuracy(deal, gt)

    exceptions = []
    for f, r in acc["top_level"].items():
        if not r["match"]:
            exceptions.append(f"{f}: extracted '{r['extracted']}' vs. stated '{r['ground_truth']}'")
    for t in acc["tranches"]:
        for f, r in t["fields"].items():
            if not r["match"]:
                exceptions.append(f"{t['class_name']} {f}: extracted '{r['extracted']}' vs. stated '{r['ground_truth']}'")

    proc = ProcedureResult(
        procedure=(
            f"Abstracted tranche terms, payment dates, servicer/trustee, and collateral "
            f"description from {deal_label} ({raw_name}) and compared each field to "
            f"independently, manually verified values from the source filing."
        ),
        result_summary=(
            f"{acc['fields_correct']} of {acc['fields_scored']} fields "
            f"({acc['overall_field_level_accuracy_pct']}%) agreed with the manually verified "
            f"values. {len(exceptions)} exception(s) noted below."
        ),
        exceptions=exceptions,
    )
    wp = DealWorkpaper(
        deal_label=deal_label,
        source_document=raw_name,
        field_level_accuracy_pct=acc["overall_field_level_accuracy_pct"],
        fields_scored=acc["fields_scored"],
        fields_correct=acc["fields_correct"],
        procedures=[proc],
    )
    return wp, {"deal": deal, "ground_truth": gt}


def _cashflow_recompute_procedure(deal_label: str, tranches: list[TrancheInput], assumptions: WaterfallAssumptions) -> ProcedureResult:
    results = run_sequential_waterfall(tranches, assumptions)
    lines = [
        f"{r.class_name}: WAL {r.wal_years:.2f} yrs, approx. pre-tax YTM {r.approx_pretax_ytm:.4f}"
        for r in results
    ]
    exceptions = []
    for r in results:
        if r.approx_pretax_ytm is not None and r.approx_pretax_ytm < 0:
            exceptions.append(
                f"{r.class_name}: computed approx. pre-tax YTM is negative ({r.approx_pretax_ytm:.4f}) under "
                f"the stated scenario assumptions -- consistent with this class receiving interest but "
                f"minimal principal within the {assumptions.collateral_term_months}-month term at this "
                f"deal's subordination level; not a computation error, flagged for reviewer awareness."
            )
    return ProcedureResult(
        procedure=(
            f"Recomputed the sequential-pay cash flow waterfall for {deal_label} under illustrative "
            f"scenario assumptions ({assumptions.annual_cpr:.0%} CPR, {assumptions.annual_default_rate:.0%} "
            f"annual default rate, {assumptions.collateral_wac:.1%} collateral WAC, "
            f"{assumptions.collateral_term_months}-month term -- chosen for this exercise, not figures "
            f"stated in the offering document) and recalculated declining balance, weighted average life "
            f"(WAL), and approximate pre-tax yield to maturity for each class."
        ),
        result_summary="; ".join(lines),
        exceptions=exceptions,
    )


def _concentration_test_procedure(deal_label: str, buckets: list[dict], bucket_field: str) -> ProcedureResult:
    strat = build_stratification_table(buckets, bucket_field=bucket_field)
    lines = []
    exceptions = []
    for row in strat.itertuples(index=False):
        pct = getattr(row, "pool_pct")
        name = getattr(row, bucket_field)
        bal = getattr(row, "total_balance")
        flag = "HIGH" if pct >= CONCENTRATION_HIGH else ("MED" if pct >= CONCENTRATION_MED else "OK")
        lines.append(f"{name}: {pct:.2f}% (${bal:,.0f}) [{flag}]")
        if flag == "HIGH":
            exceptions.append(f"{name} bucket at {pct:.2f}% of pool exceeds the {CONCENTRATION_HIGH:.0f}% concentration threshold.")
    return ProcedureResult(
        procedure=(
            f"Ran the {CONCENTRATION_HIGH:.0f}% pool-concentration test (the same test implemented in "
            f"the project's StratificationQA.bas VBA macro) against an ILLUSTRATIVE, SYNTHETIC "
            f"property-type mix for {deal_label} -- not the deal's actual collateral tape. The real "
            f"loan-level collateral tape for a CMBS deal is a separate, large data file that is not "
            f"included in the prospectus summary excerpt used elsewhere in this work paper and was not "
            f"independently sourced for this exercise. This procedure demonstrates the concentration-test "
            f"mechanics on realistic-shaped synthetic data; it is not a finding about this specific deal's "
            f"actual property-type concentration and must not be read or cited as one."
        ),
        result_summary="(synthetic data) " + "; ".join(lines),
        exceptions=exceptions,
    )


def build_abs_workpaper() -> DealWorkpaper:
    wp, _ = _document_abstraction_procedure(
        "vw_alt_2025b_424b5_excerpt.txt", "vw_alt_2025b_ground_truth.json", "VW Auto Lease Trust 2025-B (ABS)"
    )
    tranches = [
        TrancheInput("Class A-1", 1, 212_600_000, 0.04164),
        TrancheInput("Class A-2-A", 2, 305_000_000, 0.0397),
        TrancheInput("Class A-2-B", 2, 292_000_000, 0.0434),  # SOFR + 0.37% at a 4.0% illustrative SOFR level
        TrancheInput("Class A-3", 3, 597_000_000, 0.0401),
        TrancheInput("Class A-4", 4, 93_400_000, 0.0400),
    ]
    assumptions = WaterfallAssumptions(annual_cpr=0.15, annual_default_rate=0.005, collateral_wac=0.055, collateral_term_months=48)
    wp.procedures.append(_cashflow_recompute_procedure(wp.deal_label, tranches, assumptions))
    return wp


def build_cmbs_workpaper() -> DealWorkpaper:
    wp, _ = _document_abstraction_procedure(
        "benchmark_2024_v7_424b2_excerpt.txt", "benchmark_2024_v7_ground_truth.json", "Benchmark 2024-V7 (CMBS)"
    )
    tranches = [
        TrancheInput("Class A-1", 1, 1_650_000, 0.0562741),
        TrancheInput("Class A-2", 2, 33_000_000, 0.0577222),
        TrancheInput("Class A-3", 3, 533_784_000, 0.0622757),
        TrancheInput("Class A-S", 4, 86_280_000, 0.0653304),
        TrancheInput("Class B", 5, 40_602_000, 0.0707994),
    ]
    assumptions = WaterfallAssumptions(annual_cpr=0.08, annual_default_rate=0.01, collateral_wac=0.062, collateral_term_months=60)
    wp.procedures.append(_cashflow_recompute_procedure(wp.deal_label, tranches, assumptions))
    wp.procedures.append(_concentration_test_procedure(
        wp.deal_label,
        [{"property_type": "Office", "balance": 250_000_000},
         {"property_type": "Multifamily", "balance": 300_000_000},
         {"property_type": "Industrial", "balance": 180_000_000},
         {"property_type": "Retail", "balance": 91_890_000}],
        bucket_field="property_type",
    ))
    return wp


def build_all() -> dict[str, Any]:
    return {"deals": [build_abs_workpaper(), build_cmbs_workpaper()]}


if __name__ == "__main__":
    import dataclasses
    out = build_all()
    print(json.dumps({"deals": [dataclasses.asdict(d) for d in out["deals"]]}, indent=2))
