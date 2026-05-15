from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Lead(Base):
    __tablename__ = 'leads'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    phone_normalized: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    google_maps_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source_query: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default='new', index=True)
    contacted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    proposals: Mapped[list['Proposal']] = relationship(back_populates='lead')
    outreach_logs: Mapped[list['OutreachLog']] = relationship(back_populates='lead')

    __table_args__ = (
        UniqueConstraint('google_maps_url', name='uq_lead_google_maps_url'),
    )


class Proposal(Base):
    __tablename__ = 'proposals'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey('leads.id', ondelete='CASCADE'), index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    pdf_path: Mapped[str] = mapped_column(String(500), nullable=False)
    sent_via_email: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    lead: Mapped['Lead'] = relationship(back_populates='proposals')


class OutreachLog(Base):
    __tablename__ = 'outreach_logs'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey('leads.id', ondelete='CASCADE'), index=True)
    channel: Mapped[str] = mapped_column(String(30), nullable=False)  # email | call
    result: Mapped[str] = mapped_column(String(50), nullable=False)  # sent | failed | yes | no
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    lead: Mapped['Lead'] = relationship(back_populates='outreach_logs')


class CallTask(Base):
    __tablename__ = 'call_tasks'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey('leads.id', ondelete='CASCADE'), index=True)
    script_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default='pending', index=True)  # pending|queued|done|failed
    provider_call_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ScrapeCheckpoint(Base):
    __tablename__ = 'scrape_checkpoints'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    query_key: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    last_offset: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
