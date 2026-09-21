"""
Module B: simplified sequential-pay cash flow / investor analytics engine.

Explicit scope and assumptions (stated here, not buried in code, since the
project plan requires every simplifying assumption to be documented):

- Sequential pay only: no pro-rata, turbo, or interest-shortfall
  carryforward logic. Class A-1 is retired first, then the next class in
  seniority rank, etc. Classes that share a seniority_rank (e.g. Class
  A-2-A / A-2-B, which rank pari passu) split available principal pro
  rata between themselves, then the group as a whole is senior/subordinate
  to other ranks.
- Collateral amortization uses a single blended assumption: a constant
  prepayment rate (CPR, annualized) converted to a monthly rate via the
  standard SMM (single monthly mortality) conversion, plus a flat annual
  default rate applied to the scheduled balance each period (no severity/
  recovery lag modeling).
- Interest for each tranche accrues on its beginning-of-period balance at
  its coupon rate (floating tranches must be passed a fixed assumed rate
  for the run -- this engine does not simulate future SOFR paths).
- WAL is computed the standard way: sum(t * principal_paid_t) / total_principal,
  in years.
- "Approximate pre-tax yield to maturity" is the internal rate of return
  of the tranche's cash flow stream (price paid vs. coupon + principal
  received), NOT a full OAS/spread analysis.

This is a demonstration of the underlying mechanics for a portfolio
project, not a substitute for a real structured-finance model (Intex,
Bloomberg, etc.) -- say this plainly in interviews.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
import numpy_financial as npf
import pandas as pd


@dataclass
class TrancheInput:
    class_name: str
    seniority_rank: int
    initial_balance: float
    annual_coupon_rate: float  # decimal, e.g. 0.04164. For floating tranches,
    # pass the assumed all-in rate for this run (reference rate + spread).


@dataclass
class WaterfallAssumptions:
    annual_cpr: float = 0.015          # constant prepayment rate assumption (annualized)
    annual_default_rate: float = 0.005  # flat annual default rate on scheduled balance
    collateral_wac: float = 0.06        # weighted average coupon of the underlying pool
    collateral_term_months: int = 36
    payment_frequency_per_year: int = 12


@dataclass
class TrancheResult:
    class_name: str
    schedule: pd.DataFrame  # columns: period, beg_balance, interest, principal, end_balance
    wal_years: float
    approx_pretax_ytm: Optional[float]


def _smm_from_cpr(annual_cpr: float) -> float:
    """Standard CPR -> SMM (single monthly mortality) conversion."""
    return 1 - (1 - annual_cpr) ** (1 / 12)


def amortize_collateral_pool(pool_balance: float, assumptions: WaterfallAssumptions) -> pd.DataFrame:
    """
    Simplified collateral-level amortization: level-pay schedule on the
    stated WAC/term, with a constant-CPR prepayment overlay and a flat
    monthly default haircut on the scheduled balance. Returns a monthly
    DataFrame of collateral principal collections (scheduled + prepaid)
    that feed the note waterfall.
    """
    n = assumptions.collateral_term_months
    monthly_rate = assumptions.collateral_wac / 12
    smm = _smm_from_cpr(assumptions.annual_cpr)
    monthly_default = 1 - (1 - assumptions.annual_default_rate) ** (1 / 12)

    balance = pool_balance
    rows = []
    # Level payment on original balance/term (simplification: payment is not
    # re-amortized after prepayments/defaults, consistent with typical
    # auto-ABS static-pool assumption conventions for a first-pass model).
    level_payment = -npf.pmt(monthly_rate, n, pool_balance)

    for period in range(1, n + 1):
        if balance <= 0.01:
            break
        interest_due = balance * monthly_rate
        scheduled_principal = max(level_payment - interest_due, 0)
        scheduled_principal = min(scheduled_principal, balance)

        default_amount = balance * monthly_default
        default_amount = min(default_amount, balance - scheduled_principal)

        remaining_after_scheduled_and_default = balance - scheduled_principal - default_amount
        prepay_amount = max(remaining_after_scheduled_and_default, 0) * smm

        total_principal_collected = scheduled_principal + prepay_amount
        end_balance = max(balance - scheduled_principal - default_amount - prepay_amount, 0)

        rows.append({
            "period": period,
            "beg_balance": balance,
            "interest_collected": interest_due,
            "scheduled_principal": scheduled_principal,
            "default_amount": default_amount,
            "prepay_amount": prepay_amount,
            "total_principal_collected": total_principal_collected,
            "end_balance": end_balance,
        })
        balance = end_balance

    return pd.DataFrame(rows)


def run_sequential_waterfall(
    tranches: List[TrancheInput],
    assumptions: WaterfallAssumptions,
) -> List[TrancheResult]:
    """
    Allocates collateral principal collections to notes sequentially by
    seniority_rank. Tranches sharing a rank split available principal for
    that rank pro rata by their current outstanding balance.
    """
    total_initial = sum(t.initial_balance for t in tranches)
    pool_df = amortize_collateral_pool(total_initial, assumptions)

    ranks = sorted(set(t.seniority_rank for t in tranches))
    balances = {t.class_name: t.initial_balance for t in tranches}
    coupons = {t.class_name: t.annual_coupon_rate for t in tranches}
    rank_of = {t.class_name: t.seniority_rank for t in tranches}

    schedules = {t.class_name: [] for t in tranches}

    for _, row in pool_df.iterrows():
        available_principal = row["total_principal_collected"]

        for cls, bal in balances.items():
            interest = bal * (coupons[cls] / 12)
            schedules[cls].append({
                "period": row["period"],
                "beg_balance": bal,
                "interest": interest,
                "principal": 0.0,  # filled in below
                "end_balance": bal,  # placeholder, updated below
            })

        for rank in ranks:
            if available_principal <= 0.01:
                break
            group = [t.class_name for t in tranches if rank_of[t.class_name] == rank]
            group_balance = sum(balances[c] for c in group)
            if group_balance <= 0.01:
                continue
            pay_to_group = min(available_principal, group_balance)
            for cls in group:
                share = (balances[cls] / group_balance) if group_balance > 0 else 0
                pay = pay_to_group * share
                balances[cls] = max(balances[cls] - pay, 0)
                schedules[cls][-1]["principal"] = pay
                schedules[cls][-1]["end_balance"] = balances[cls]
            available_principal -= pay_to_group

        # Any tranche not touched this period still needs end_balance set correctly
        for cls in balances:
            if schedules[cls][-1]["end_balance"] != balances[cls] and schedules[cls][-1]["principal"] == 0.0:
                schedules[cls][-1]["end_balance"] = balances[cls]

    results = []
    for t in tranches:
        df = pd.DataFrame(schedules[t.class_name])
        wal = _weighted_average_life(df, t.initial_balance, assumptions.payment_frequency_per_year)
        ytm = _approx_ytm(df, t.initial_balance, assumptions.payment_frequency_per_year)
        results.append(TrancheResult(class_name=t.class_name, schedule=df, wal_years=wal, approx_pretax_ytm=ytm))
    return results


def _weighted_average_life(schedule: pd.DataFrame, initial_balance: float, periods_per_year: int) -> float:
    if schedule.empty or initial_balance <= 0:
        return 0.0
    weighted = (schedule["period"] * schedule["principal"]).sum()
    total_principal = schedule["principal"].sum()
    if total_principal <= 0:
        return 0.0
    wal_periods = weighted / total_principal
    return round(wal_periods / periods_per_year, 3)


def _approx_ytm(schedule: pd.DataFrame, initial_balance: float, periods_per_year: int) -> Optional[float]:
    """IRR of [-initial_balance, cf_1, cf_2, ...] where cf_t = interest + principal, annualized."""
    if schedule.empty:
        return None
    cash_flows = [-initial_balance] + list((schedule["interest"] + schedule["principal"]).values)
    try:
        monthly_irr = npf.irr(cash_flows)
    except Exception:
        return None
    if monthly_irr is None or np.isnan(monthly_irr):
        return None
    annualized = (1 + monthly_irr) ** periods_per_year - 1
    return round(float(annualized), 5)


def build_stratification_table(asset_records: List[dict], bucket_field: str, value_field: str = "balance") -> pd.DataFrame:
    """
    Module B stratification helper: given a list of asset-level records
    (e.g. from an ABS-EE data tape -- FICO band, loan age, state, etc.),
    compute pool percentage by bucket. This mirrors "recompute statistical
    attributes, stratification tables, and pool percentages" from the JD.
    """
    df = pd.DataFrame(asset_records)
    if df.empty:
        return pd.DataFrame(columns=[bucket_field, "total_balance", "pool_pct"])
    grouped = df.groupby(bucket_field)[value_field].sum().reset_index()
    grouped = grouped.rename(columns={value_field: "total_balance"})
    total = grouped["total_balance"].sum()
    grouped["pool_pct"] = (grouped["total_balance"] / total * 100).round(2) if total else 0.0
    return grouped.sort_values("total_balance", ascending=False).reset_index(drop=True)
