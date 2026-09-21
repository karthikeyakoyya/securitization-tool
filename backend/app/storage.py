"""
SQLite storage for extracted deal data (Module A output), via SQLAlchemy.
Kept deliberately simple -- one JSON blob column per deal rather than a
fully normalized schema, since the review UI reads/writes whole
DealExtraction objects and a normalized schema would add migration
overhead with no real benefit at this project's scale.
"""
from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


class DealRecord(Base):
    __tablename__ = "deals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_document = Column(String, nullable=False)
    source_url = Column(String, nullable=True)
    issuer_trust_name = Column(String, nullable=True)
    extraction_json = Column(Text, nullable=False)  # full DealExtraction, serialized
    accuracy_json = Column(Text, nullable=True)      # output of score_field_level_accuracy, if scored
    created_at = Column(DateTime, default=datetime.utcnow)


def get_engine(db_path: str = "sqlite:///./securitization.db"):
    return create_engine(db_path, connect_args={"check_same_thread": False})


def init_db(engine):
    Base.metadata.create_all(engine)


def get_session(engine):
    Session = sessionmaker(bind=engine)
    return Session()


def save_deal(session, deal_extraction, accuracy: dict | None = None) -> DealRecord:
    record = DealRecord(
        source_document=deal_extraction.source_document,
        source_url=deal_extraction.source_url,
        issuer_trust_name=deal_extraction.issuer_trust_name,
        extraction_json=deal_extraction.model_dump_json(),
        accuracy_json=json.dumps(accuracy) if accuracy else None,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def list_deals(session):
    return session.query(DealRecord).order_by(DealRecord.created_at.desc()).all()
