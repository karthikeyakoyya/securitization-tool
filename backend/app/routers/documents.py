from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import storage
from ..extraction import HeuristicExtractor, score_field_level_accuracy

router = APIRouter(prefix="/api/documents", tags=["documents"])

SAMPLE_RAW_DIR = Path(__file__).resolve().parents[2] / "sample_data" / "raw"
SAMPLE_GT_DIR = Path(__file__).resolve().parents[2] / "sample_data" / "ground_truth"


def get_db():
    engine = storage.get_engine()
    storage.init_db(engine)
    session = storage.get_session(engine)
    try:
        yield session
    finally:
        session.close()


@router.get("/sample-files")
def list_sample_files():
    """List the raw sample documents bundled with the repo."""
    if not SAMPLE_RAW_DIR.exists():
        return []
    return [p.name for p in SAMPLE_RAW_DIR.glob("*.txt")]


@router.post("/extract-sample/{filename}")
def extract_sample(filename: str, db: Session = Depends(get_db)):
    """
    Run the heuristic extractor against one of the bundled sample raw
    documents, score it against ground truth if available, and persist
    the result.
    """
    raw_path = SAMPLE_RAW_DIR / filename
    if not raw_path.exists():
        raise HTTPException(404, f"Sample file {filename} not found")

    raw_text = raw_path.read_text()
    extractor = HeuristicExtractor()
    deal = extractor.extract(raw_text, source_document=filename)

    accuracy = None
    # Ground-truth filenames drop whatever SEC form suffix the raw filename
    # carries (_424b5_excerpt, _424b2_excerpt, ...) in favor of
    # "_ground_truth" -- generalized from a single hardcoded suffix so a
    # second asset class's filename (a different form type) still resolves.
    gt_stem = re.sub(r"_\d{3}[a-z]\d(?:_excerpt)?$", "_ground_truth", raw_path.stem)
    gt_path = SAMPLE_GT_DIR / (gt_stem + ".json")
    if gt_path.exists():
        ground_truth = json.loads(gt_path.read_text())
        accuracy = score_field_level_accuracy(deal, ground_truth)

    record = storage.save_deal(db, deal, accuracy)
    return {
        "id": record.id,
        "extraction": json.loads(deal.model_dump_json()),
        "accuracy": accuracy,
        "flagged_fields": deal.flagged_fields(),
    }


@router.get("")
def list_documents(db: Session = Depends(get_db)):
    records = storage.list_deals(db)
    return [
        {
            "id": r.id,
            "source_document": r.source_document,
            "issuer_trust_name": r.issuer_trust_name,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "accuracy": json.loads(r.accuracy_json) if r.accuracy_json else None,
        }
        for r in records
    ]


@router.get("/{deal_id}")
def get_document(deal_id: int, db: Session = Depends(get_db)):
    record = db.get(storage.DealRecord, deal_id)
    if not record:
        raise HTTPException(404, "Deal not found")
    return {
        "id": record.id,
        "extraction": json.loads(record.extraction_json),
        "accuracy": json.loads(record.accuracy_json) if record.accuracy_json else None,
    }
