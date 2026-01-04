from datetime import datetime, date
from sqlalchemy import Column, Integer, String, Float, Date, DateTime, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Alert(Base):
    __tablename__ = "alerts"
    id = Column(Integer, primary_key=True)
    ts = Column(DateTime(timezone=True), nullable=False)
    underlying = Column(String(16), nullable=False)
    option_ticker = Column(String(64), nullable=False)
    call_put = Column(String(4), nullable=False)
    strike = Column(Float, nullable=False)
    expiry = Column(Date, nullable=False)
    dte = Column(Integer, nullable=False)
    premium_total = Column(Float, nullable=False)
    contracts_total = Column(Float, nullable=False)
    prints_count = Column(Integer, nullable=False)
    duration_sec = Column(Float, nullable=False)
    ask_side_ratio = Column(Float, nullable=False)
    sweep_score = Column(Float, nullable=True)
    oi = Column(Float, nullable=True)
    vol_oi_ratio = Column(Float, nullable=True)
    otm_pct = Column(Float, nullable=True)
    setup_type = Column(String(32), nullable=False)
    score_total = Column(Float, nullable=False)
    score_components_json = Column(Text, nullable=False)
    tags_json = Column(Text, nullable=False)
    template_type = Column(String(32), nullable=False)
    cluster_key = Column(String(128), nullable=False, index=True)


class DedupeState(Base):
    __tablename__ = "dedupe_state"
    cluster_key = Column(String(128), primary_key=True)
    last_alert_ts = Column(DateTime(timezone=True), nullable=False)
    last_score = Column(Float, nullable=False)
    last_premium = Column(Float, nullable=False)
