from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Lead
from app.services.maps_scraper import ScrapedLead
from app.services.utils import normalize_email, normalize_phone

settings = get_settings()


class LeadService:
    def __init__(self, db: Session):
        self.db = db

    def create_or_skip(self, scraped: ScrapedLead, source_query: str) -> tuple[Lead | None, str]:
        normalized_phone = normalize_phone(scraped.phone, settings.default_region)
        normalized_email = normalize_email(scraped.email)

        # Business requirement: lead must have phone and must not have website.
        if scraped.website:
            return None, 'skipped_has_website'
        if not normalized_phone:
            return None, 'skipped_missing_phone'

        # Soft dedupe by phone/email/name before insert.
        duplicate = self.db.scalar(
            select(Lead).where(
                or_(
                    and_(Lead.phone_normalized.is_not(None), Lead.phone_normalized == normalized_phone),
                    and_(Lead.email.is_not(None), Lead.email == normalized_email),
                    and_(Lead.google_maps_url.is_not(None), Lead.google_maps_url == scraped.google_maps_url),
                )
            )
        )
        if duplicate:
            return duplicate, 'duplicate'

        lead = Lead(
            business_name=scraped.business_name,
            category=scraped.category,
            address=scraped.address,
            phone=scraped.phone,
            phone_normalized=normalized_phone,
            email=normalized_email,
            website=scraped.website,
            google_maps_url=scraped.google_maps_url,
            source_query=source_query,
            status='new',
        )
        self.db.add(lead)
        try:
            self.db.commit()
            self.db.refresh(lead)
            return lead, 'created'
        except IntegrityError:
            self.db.rollback()
            return None, 'duplicate'

    def get_pending_for_outreach(self, limit: int) -> list[Lead]:
        stmt = (
            select(Lead)
            .where(Lead.contacted.is_(False))
            .where(Lead.status.in_(['new', 'contacted']))
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def set_status(self, lead_id: int, status: str) -> Lead | None:
        lead = self.db.get(Lead, lead_id)
        if not lead:
            return None
        lead.status = status
        self.db.commit()
        self.db.refresh(lead)
        return lead
