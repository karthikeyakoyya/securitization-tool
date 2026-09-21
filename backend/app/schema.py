"""
Module A schema: the structured fields we abstract from a securitization
offering/legal document. Defined up front (per the project plan) so
extraction has a concrete target instead of vague "pull out the important
stuff."
"""
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class CouponType(str, Enum):
    FIXED = "fixed"
    FLOATING = "floating"


class Tranche(BaseModel):
    class_name: str = Field(..., description="e.g. 'Class A-1'")
    seniority_rank: int = Field(..., description="1 = most senior")
    initial_principal_balance: float
    coupon_type: CouponType
    coupon_rate: Optional[float] = Field(
        None, description="Fixed annual coupon as a decimal, e.g. 0.04164 for 4.164%"
    )
    reference_rate: Optional[str] = Field(None, description="e.g. 'SOFR' if floating")
    spread: Optional[float] = Field(None, description="Spread over reference rate, as a decimal")
    final_scheduled_payment_date: Optional[date] = None
    credit_rating: Optional[str] = None
    rating_agency: Optional[str] = None

    # Confidence / traceability -- populated by the extraction layer, not
    # part of the "ground truth" shape itself.
    confidence: Optional[float] = Field(
        None, description="0-1 confidence score from the extraction layer, if available"
    )
    flagged_for_review: bool = False
    flag_reason: Optional[str] = None
    source_snippet: Optional[str] = Field(
        None, description="Short excerpt the value was pulled from, for traceability"
    )


class CreditEnhancement(BaseModel):
    reserve_account_pct_of_initial_pool: Optional[float] = None
    initial_overcollateralization_amount: Optional[float] = None
    initial_overcollateralization_pct: Optional[float] = None


class DealExtraction(BaseModel):
    """The full set of Module A fields for one document/deal."""

    source_document: str
    source_url: Optional[str] = None

    issuer_trust_name: Optional[str] = None
    deal_name_series: Optional[str] = None
    closing_date: Optional[date] = None
    payment_frequency: Optional[str] = None
    payment_day_of_month: Optional[int] = None
    first_payment_date: Optional[date] = None

    servicer_name: Optional[str] = None
    trustee_name: Optional[str] = None
    collateral_type: Optional[str] = None

    aggregate_pool_balance_at_cutoff: Optional[float] = None
    cutoff_date: Optional[date] = None

    tranches: List[Tranche] = Field(default_factory=list)
    credit_enhancement: Optional[CreditEnhancement] = None
    key_covenants_triggers: List[str] = Field(default_factory=list)

    def flagged_fields(self) -> List[str]:
        """Convenience: list tranche/field names flagged for human review."""
        flags = []
        for t in self.tranches:
            if t.flagged_for_review:
                flags.append(f"{t.class_name}: {t.flag_reason or 'flagged'}")
        return flags
