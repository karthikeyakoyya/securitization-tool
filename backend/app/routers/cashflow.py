from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import List, Optional

import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..cashflow_engine import (
    TrancheInput,
    WaterfallAssumptions,
    build_stratification_table,
    run_sequential_waterfall,
)
from ..excel_export import export_cashflow_workbook

router = APIRouter(prefix="/api/cashflow", tags=["cashflow"])

OUTPUT_DIR = Path(__file__).resolve().parents[2] / "sample_data" / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


class TrancheInputModel(BaseModel):
    class_name: str
    seniority_rank: int
    initial_balance: float
    annual_coupon_rate: float


class AssumptionsModel(BaseModel):
    annual_cpr: float = 0.015
    annual_default_rate: float = 0.005
    collateral_wac: float = 0.06
    collateral_term_months: int = 36
    payment_frequency_per_year: int = 12


class StratRecordModel(BaseModel):
    bucket: str
    balance: float


class RunWaterfallRequest(BaseModel):
    tranches: List[TrancheInputModel]
    assumptions: AssumptionsModel = AssumptionsModel()
    stratification_records: Optional[List[StratRecordModel]] = None
    stratification_bucket_label: str = "bucket"


@router.post("/run")
def run_waterfall(req: RunWaterfallRequest):
    tranche_inputs = [
        TrancheInput(
            class_name=t.class_name,
            seniority_rank=t.seniority_rank,
            initial_balance=t.initial_balance,
            annual_coupon_rate=t.annual_coupon_rate,
        )
        for t in req.tranches
    ]
    assumptions = WaterfallAssumptions(**req.assumptions.model_dump())

    results = run_sequential_waterfall(tranche_inputs, assumptions)

    response = {
        "assumptions": req.assumptions.model_dump(),
        "tranches": [
            {
                "class_name": r.class_name,
                "wal_years": r.wal_years,
                "approx_pretax_ytm": r.approx_pretax_ytm,
                "schedule": r.schedule.to_dict(orient="records"),
            }
            for r in results
        ],
    }
    return response


@router.post("/export-excel")
def export_excel(req: RunWaterfallRequest):
    tranche_inputs = [
        TrancheInput(
            class_name=t.class_name,
            seniority_rank=t.seniority_rank,
            initial_balance=t.initial_balance,
            annual_coupon_rate=t.annual_coupon_rate,
        )
        for t in req.tranches
    ]
    assumptions = WaterfallAssumptions(**req.assumptions.model_dump())
    results = run_sequential_waterfall(tranche_inputs, assumptions)

    strat_df = None
    if req.stratification_records:
        records = [{"bucket": s.bucket, "balance": s.balance} for s in req.stratification_records]
        strat_df = build_stratification_table(records, bucket_field="bucket", value_field="balance")

    assumptions_note = (
        f"Sequential-pay simplified model. CPR={assumptions.annual_cpr:.2%}, "
        f"annual default rate={assumptions.annual_default_rate:.2%}, "
        f"collateral WAC={assumptions.collateral_wac:.2%}, "
        f"term={assumptions.collateral_term_months}mo. "
        f"No pro-rata/turbo/trigger logic modeled -- see README for full assumption list."
    )

    filename = f"cashflow_{uuid.uuid4().hex[:8]}.xlsx"
    output_path = OUTPUT_DIR / filename
    export_cashflow_workbook(results, str(output_path), stratification=strat_df, assumptions_note=assumptions_note)

    return FileResponse(
        path=str(output_path),
        filename="securitization_cashflow_export.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/sample-request")
def sample_request():
    """
    A ready-to-use example request body, built from the real VW ALT 2025-B
    tranche terms in sample_data/ground_truth/, so the frontend (or curl)
    can hit /run and /export-excel without hand-typing tranche data.
    """
    return {
        "tranches": [
            {"class_name": "Class A-1", "seniority_rank": 1, "initial_balance": 212_600_000, "annual_coupon_rate": 0.04164},
            {"class_name": "Class A-2-A", "seniority_rank": 2, "initial_balance": 305_000_000, "annual_coupon_rate": 0.0397},
            {"class_name": "Class A-2-B", "seniority_rank": 2, "initial_balance": 292_000_000, "annual_coupon_rate": 0.045},
            {"class_name": "Class A-3", "seniority_rank": 3, "initial_balance": 597_000_000, "annual_coupon_rate": 0.0401},
            {"class_name": "Class A-4", "seniority_rank": 4, "initial_balance": 93_400_000, "annual_coupon_rate": 0.04},
        ],
        "assumptions": {
            "annual_cpr": 0.015,
            "annual_default_rate": 0.005,
            "collateral_wac": 0.06,
            "collateral_term_months": 37,
            "payment_frequency_per_year": 12,
        },
        "stratification_records": [
            {"bucket": "FICO 720-759", "balance": 450_000_000},
            {"bucket": "FICO 760-799", "balance": 520_000_000},
            {"bucket": "FICO 800+", "balance": 380_000_000},
            {"bucket": "FICO 680-719", "balance": 240_000_000},
            {"bucket": "FICO <680", "balance": 159_271_144.90},
        ],
        "note": (
            "Class A-2-B's annual_coupon_rate here is an ASSUMED all-in rate "
            "(SOFR + 0.37% spread, illustratively assumed SOFR ~4.13%) for "
            "this run -- this engine does not simulate future SOFR paths. "
            "Stratification buckets are illustrative, not the real deal's "
            "actual FICO distribution (that requires pulling the ABS-EE tape)."
        ),
    }
