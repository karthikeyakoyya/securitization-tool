"""
Module A: extraction pipeline.

Two extraction backends are provided:

1. `HeuristicExtractor` -- regex/pattern based, works fully offline with no
   API key. This is what the sample_data/ demo runs against. It is
   intentionally narrow (built against the specific table format SEC ABS
   424B5 filings use for their "Summary of Terms" tranche table) -- this
   is a portfolio project, not a production parser, and that limitation
   should be stated plainly in interviews.

2. `LLMExtractor` -- pluggable structured-output extraction via the OpenAI
   API, for the fields the regex layer can't reliably get (e.g. covenants
   described in free-flowing prose). Requires OPENAI_API_KEY to be set;
   falls back to a clear error if it isn't, rather than silently returning
   nothing.

Both feed the same `DealExtraction` schema (see schema.py), and both run
through the same confidence-flagging step in `flag_low_confidence_fields`
so the review UI treats them identically.
"""
from __future__ import annotations

import os
import re
from datetime import date, datetime
from typing import List, Optional

from .schema import CouponType, CreditEnhancement, DealExtraction, Tranche

# --------------------------------------------------------------------------
# Heuristic (regex) extractor -- no external API required.
# --------------------------------------------------------------------------

_TRANCHE_ROW_RE = re.compile(
    r"""(?P<class_name>Class\s+[A-Z]{1,2}(?:-[A-Z0-9]+)*)\s*\|\s*
        \$?(?P<balance>[\d,]+)\s*\|\s*
        (?P<rate_str>[^|]+?)\s*\|\s*
        (?P<fourth_col>[^|\n]+)""",
    re.VERBOSE,
)

_DATE_RE = re.compile(r"([A-Za-z]+\s+\d{1,2},\s+\d{4})")

_FIXED_RATE_RE = re.compile(r"([\d.]+)%\s*\(fixed\)")
_FLOAT_RATE_RE = re.compile(r"(SOFR|LIBOR|Prime)\s*Rate\s*\+\s*([\d.]+)%\s*\(float", re.IGNORECASE)

# Some field labels differ between asset classes (auto-ABS uses
# "Servicer/Sponsor:" and "Indenture Trustee:"; CMBS conduit deals use
# "Master Servicer:" and "Trustee:"). Each field can list more than one
# candidate pattern -- the first one that matches in the document wins.
# This is a real, documented extension from testing the extractor against
# a second, structurally different asset class (see README "Extending to
# a second asset class" for what did and didn't carry over cleanly).
_FIELD_PATTERNS = {
    "issuer_trust_name": [r"Issuing Entity/Trust:\s*(.+?)(?:,\s*a\s|\n)"],
    "servicer_name": [
        r"Servicer/Sponsor:\s*(.+?)(?:\s*\(|,\s*a\s|\n)",
        r"Master Servicer:\s*(.+?)(?:\.\s*\n|\n)",
    ],
    "trustee_name": [
        r"Indenture Trustee:\s*(.+)",
        r"^Trustee:\s*(.+)",
    ],
    "collateral_type": [r"Collateral Type:\s*(.+)"],
    "closing_date": [r"Closing Date:\s*(?:on or about\s*)?(.+)"],
    "first_payment_date": [r"First Payment Date:\s*(.+)"],
    "cutoff_date": [r"cutoff date,?\s*(.+?)\)"],
    "aggregate_pool_balance_at_cutoff": [r"Aggregate securitization value.*?:\s*\$([\d,\.]+)"],
    "reserve_pct": [r"Reserve account:.*?>=\s*([\d.]+)%"],
    "oc_amount": [r"Overcollateralization:\s*initial amount\s*\$([\d,\.]+)"],
    "oc_pct": [r"Overcollateralization:.*?\(([\d.]+)%"],
}


def _parse_date_loose(s: str) -> Optional[date]:
    s = s.strip().rstrip(".")
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _to_float(s: str) -> Optional[float]:
    try:
        return float(s.replace(",", ""))
    except (ValueError, AttributeError):
        return None


class HeuristicExtractor:
    """Regex-based extractor for the SEC ABS prospectus summary-of-terms
    format used in sample_data/raw/. Flags anything it can't confidently
    parse rather than guessing.
    """

    def extract(self, raw_text: str, source_document: str, source_url: str = None) -> DealExtraction:
        deal = DealExtraction(source_document=source_document, source_url=source_url)

        for field, patterns in _FIELD_PATTERNS.items():
            m = None
            for pattern in patterns:
                m = re.search(pattern, raw_text, re.IGNORECASE | re.MULTILINE)
                if m:
                    break
            if not m:
                continue
            value = m.group(1).strip()
            if field in ("closing_date", "first_payment_date", "cutoff_date"):
                setattr(deal, field, _parse_date_loose(value))
            elif field == "aggregate_pool_balance_at_cutoff":
                deal.aggregate_pool_balance_at_cutoff = _to_float(value)
            elif field == "reserve_pct":
                deal.credit_enhancement = deal.credit_enhancement or CreditEnhancement()
                deal.credit_enhancement.reserve_account_pct_of_initial_pool = _to_float(value) / 100 if _to_float(value) else None
            elif field == "oc_amount":
                deal.credit_enhancement = deal.credit_enhancement or CreditEnhancement()
                deal.credit_enhancement.initial_overcollateralization_amount = _to_float(value)
            elif field == "oc_pct":
                deal.credit_enhancement = deal.credit_enhancement or CreditEnhancement()
                deal.credit_enhancement.initial_overcollateralization_pct = _to_float(value) / 100 if _to_float(value) else None
            else:
                setattr(deal, field, value)

        deal.payment_frequency = "monthly" if "day of each month" in raw_text else None
        pm = re.search(r"(\d{1,2})(?:th|st|nd|rd)\s+day of each month", raw_text)
        if pm:
            deal.payment_day_of_month = int(pm.group(1))

        # Tranches
        seniority = 0
        seen_ranks = {}
        for m in _TRANCHE_ROW_RE.finditer(raw_text):
            class_name = m.group("class_name").strip()
            balance = _to_float(m.group("balance"))
            rate_str = m.group("rate_str").strip()
            # The 4th column is a final-payment date in the ABS table
            # format but a rate-type label (Fixed/WAC/WAC Cap) in the CMBS
            # table format -- only parse it as a date when it looks like
            # one, and treat a non-date 4th column as extra rate-type
            # context rather than forcing a parse failure.
            fourth_col = m.group("fourth_col").strip()
            date_m = _DATE_RE.search(fourth_col)
            final_date = _parse_date_loose(date_m.group(1)) if date_m else None
            rate_type_label = fourth_col if not date_m else None

            fixed_m = _FIXED_RATE_RE.search(rate_str)
            float_m = _FLOAT_RATE_RE.search(rate_str)

            # Seniority: A-1 < A-2 (A-2-A/A-2-B share rank) < A-3 < A-4 ...
            # Only auto-ABS-style "Class A-<digit>" names carry a numeric
            # rank in the label itself. CMBS-style classes (Class A-S,
            # Class B, Class C ...) don't -- for those we fall back to
            # document order, which is a real, honest limitation: it's
            # only correct because this document happens to list classes
            # in seniority order, not because the extractor understands
            # CMBS subordination structure.
            base_class = re.match(r"Class A-(\d)(?:-[A-Z])?$", class_name)
            rank = int(base_class.group(1)) if base_class else None

            tranche = Tranche(
                class_name=class_name,
                seniority_rank=rank or (seniority + 1),
                initial_principal_balance=balance or 0.0,
                coupon_type=CouponType.FLOATING if float_m else CouponType.FIXED,
                coupon_rate=float(fixed_m.group(1)) / 100 if fixed_m else None,
                reference_rate=float_m.group(1).upper() if float_m else None,
                spread=float(float_m.group(2)) / 100 if float_m else None,
                final_scheduled_payment_date=final_date,
                credit_rating=None,
                source_snippet=m.group(0)[:160],
            )
            if not fixed_m and not float_m:
                tranche.flagged_for_review = True
                if rate_type_label and "WAC" in rate_type_label.upper():
                    # Real, known schema gap: a WAC/WAC-Cap pass-through
                    # rate (varies with the pool's weighted average coupon)
                    # isn't cleanly "fixed" or "floating" under this
                    # project's binary CouponType enum. Rather than force
                    # a classification, this is left flagged and defaults
                    # to FIXED per the branch below -- documented as a
                    # known limitation, not silently patched over.
                    tranche.flag_reason = (
                        f"Rate type '{rate_type_label}' (pool-WAC-linked) has no clean fit in "
                        "the fixed/floating schema; defaulted to fixed and flagged"
                    )
                else:
                    tranche.flag_reason = "Could not parse coupon type/rate from row text"
            if not tranche.credit_rating:
                tranche.flagged_for_review = True
                tranche.flag_reason = (tranche.flag_reason + "; " if tranche.flag_reason else "") + \
                    "Credit rating not present in summary-of-terms table"
            deal.tranches.append(tranche)
            seniority += 1

        # Covenants/triggers -- pull the labelled block if present, else flag.
        cov_block = re.search(
            r"Key Covenants/Triggers.*?:\s*\n(.*?)(?:\n===|\Z)", raw_text, re.DOTALL
        )
        if cov_block:
            lines = [l.strip("- ").strip() for l in cov_block.group(1).splitlines() if l.strip().startswith("-")]
            deal.key_covenants_triggers = lines
        else:
            deal.key_covenants_triggers = []

        return deal


class LLMExtractor:
    """Pluggable OpenAI-backed extractor for fields the regex layer misses
    (long-form covenant language, non-standard table layouts, PDFs with
    inconsistent formatting). Not wired to a live key in this repo --
    implement `_call_openai` with your own key to activate it.
    """

    def __init__(self, model: str = "gpt-4o-mini"):
        self.model = model
        self.api_key = os.environ.get("OPENAI_API_KEY")

    def extract(self, raw_text: str, source_document: str, source_url: str = None) -> DealExtraction:
        if not self.api_key:
            raise RuntimeError(
                "OPENAI_API_KEY not set. The LLM extraction layer is pluggable but "
                "inactive in this environment -- use HeuristicExtractor for the "
                "offline demo, or set OPENAI_API_KEY and implement _call_openai() "
                "to activate this path."
            )
        raise NotImplementedError(
            "Wire this up to your OpenAI account: build a structured-output "
            "prompt per DealExtraction/Tranche field (see schema.py), call "
            "the API, and parse the JSON response into a DealExtraction."
        )


def score_field_level_accuracy(extracted: DealExtraction, ground_truth: dict) -> dict:
    """
    Module A evaluation: compare extracted top-level fields and tranche
    fields against a manually-verified ground truth dict (see
    sample_data/ground_truth/*.json). Returns per-field match booleans and
    an overall accuracy percentage. This is the "real accuracy number,
    with honest failure cases" the project plan calls for.
    """
    results = {"top_level": {}, "tranches": []}
    top_fields = [
        "issuer_trust_name", "deal_name_series", "closing_date",
        "payment_frequency", "payment_day_of_month", "first_payment_date",
        "servicer_name", "trustee_name", "collateral_type",
        "aggregate_pool_balance_at_cutoff", "cutoff_date",
    ]
    def _jsonable(v):
        if hasattr(v, "isoformat"):
            return v.isoformat()
        if hasattr(v, "value"):  # enum
            return v.value
        return v

    def _values_match(ex_v, gt_v) -> bool:
        """Fixed from an earlier version of this scorer, which (a) treated
        two None values as a mismatch -- so a field correctly left blank
        by both the extractor and the ground truth counted against
        accuracy -- and (b) compared numbers as raw strings, so a valid
        212600000.0 vs 212600000 (float vs int, same value) also counted
        as a miss. Both were silent accuracy under-counts that affected
        every scored document, not just a new one; fixing them here
        applies retroactively and evenly rather than only to whichever
        document is scored next.
        """
        if ex_v is None and gt_v is None:
            return True
        if ex_v is None or gt_v is None:
            return False
        try:
            # Tolerance, not exact equality: a rate parsed as 4.164 / 100
            # lands on 0.041639999999999996 in binary floating point, not
            # exactly 0.04164 -- a correct extraction, wrongly scored as
            # wrong under exact equality.
            return abs(float(ex_v) - float(gt_v)) < 1e-6
        except (TypeError, ValueError):
            pass
        return str(ex_v).strip().lower() == str(gt_v).strip().lower()

    total, correct = 0, 0
    for f in top_fields:
        gt_val = ground_truth.get(f)
        ex_val = getattr(extracted, f, None)
        match = _values_match(_jsonable(ex_val), gt_val)
        results["top_level"][f] = {"extracted": _jsonable(ex_val), "ground_truth": _jsonable(gt_val), "match": match}
        total += 1
        correct += int(match)

    gt_tranches = {t["class_name"]: t for t in ground_truth.get("tranches", [])}
    for t in extracted.tranches:
        gt_t = gt_tranches.get(t.class_name, {})
        field_matches = {}
        for f in ("initial_principal_balance", "coupon_type", "coupon_rate", "final_scheduled_payment_date"):
            ex_v = _jsonable(getattr(t, f, None))
            gt_v = gt_t.get(f)
            match = _values_match(ex_v, gt_v)
            field_matches[f] = {"extracted": ex_v, "ground_truth": gt_v, "match": match}
            total += 1
            correct += int(match)
        results["tranches"].append({"class_name": t.class_name, "fields": field_matches})

    results["overall_field_level_accuracy_pct"] = round(100 * correct / total, 1) if total else 0.0
    results["fields_scored"] = total
    results["fields_correct"] = correct
    return results
