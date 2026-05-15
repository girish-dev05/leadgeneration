from collections import Counter
import csv
from datetime import datetime
import io
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import Base, SessionLocal, engine, get_db
from app.models import CallTask, Lead, OutreachLog, Proposal, ScrapeCheckpoint
from app.services.lead_service import LeadService
from app.services.maps_scraper import scrape_google_maps_sync
from app.services.outreach_service import OutreachService

settings = get_settings()
app = FastAPI(title=settings.app_name)
templates = Jinja2Templates(directory='app/templates')
proposal_storage = Path('storage/proposals')
proposal_storage.mkdir(parents=True, exist_ok=True)

app.mount('/static', StaticFiles(directory='app/static'), name='static')
app.mount('/proposals', StaticFiles(directory='storage/proposals'), name='proposals')

scheduler = BackgroundScheduler()


class ScrapeRequest(BaseModel):
    query: str = Field(min_length=3)
    max_results: int = Field(default=20, ge=1, le=100)
    resume_from_last: bool = False


class StatusUpdateRequest(BaseModel):
    status: str


class CallOutcomeRequest(BaseModel):
    outcome: str  # yes | no | later
    notes: str | None = None


@app.on_event('startup')
def on_startup():
    try:
        initialize_database()
        Base.metadata.create_all(bind=engine)
    except Exception as exc:
        print(f'[startup-warning] Database init failed: {exc}')

    if settings.outreach_enabled and not scheduler.running:
        scheduler.add_job(run_scheduled_outreach, 'interval', minutes=30, id='outreach_job', replace_existing=True)
        scheduler.start()


@app.on_event('shutdown')
def on_shutdown():
    if scheduler.running:
        scheduler.shutdown(wait=False)


def run_scheduled_outreach():
    db = SessionLocal()
    try:
        OutreachService(db).run_batch(batch_size=settings.outreach_batch_size)
    finally:
        db.close()


def initialize_database():
    # Render Postgres DATABASE_URL already points to an existing database.
    if settings.is_postgres:
        return

    import pymysql

    conn = pymysql.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        connect_timeout=5,
        read_timeout=10,
        write_timeout=10,
        autocommit=True,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{settings.mysql_db}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
    finally:
        conn.close()


def normalize_query_key(query: str) -> str:
    return ' '.join(query.strip().lower().split())


@app.get('/', response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    db_warning = None
    try:
        leads = db.scalars(select(Lead).order_by(Lead.created_at.desc()).limit(200)).all()
    except OperationalError:
        leads = []
        db_warning = 'Database is not reachable. Verify database service and environment variables.'
    status_counts = Counter([lead.status for lead in leads])
    won_leads = [lead for lead in leads if lead.status in ('interested', 'won')]
    lead_ids = [lead.id for lead in leads]

    latest_proposal_by_lead: dict[int, Proposal] = {}
    latest_email_log_by_lead: dict[int, OutreachLog] = {}
    latest_call_task_by_lead: dict[int, CallTask] = {}
    if lead_ids:
        proposals = db.scalars(
            select(Proposal)
            .where(Proposal.lead_id.in_(lead_ids))
            .order_by(Proposal.lead_id.asc(), Proposal.created_at.desc())
        ).all()
        for proposal in proposals:
            latest_proposal_by_lead.setdefault(proposal.lead_id, proposal)

        email_logs = db.scalars(
            select(OutreachLog)
            .where(OutreachLog.lead_id.in_(lead_ids))
            .where(OutreachLog.channel == 'email')
            .order_by(OutreachLog.lead_id.asc(), OutreachLog.created_at.desc())
        ).all()
        for email_log in email_logs:
            latest_email_log_by_lead.setdefault(email_log.lead_id, email_log)

        call_tasks = db.scalars(
            select(CallTask)
            .where(CallTask.lead_id.in_(lead_ids))
            .order_by(CallTask.lead_id.asc(), CallTask.created_at.desc())
        ).all()
        for call_task in call_tasks:
            latest_call_task_by_lead.setdefault(call_task.lead_id, call_task)

    lead_rows = []
    for lead in leads:
        proposal = latest_proposal_by_lead.get(lead.id)
        email_log = latest_email_log_by_lead.get(lead.id)
        call_task = latest_call_task_by_lead.get(lead.id)

        proposal_url = None
        if proposal and proposal.pdf_path:
            pdf_name = Path(proposal.pdf_path).name
            proposal_url = f'/proposals/{pdf_name}'

        lead_rows.append(
            {
                'lead': lead,
                'proposal_url': proposal_url,
                'proposal_sent_via_email': proposal.sent_via_email if proposal else None,
                'email_result': email_log.result if email_log else None,
                'email_details': email_log.details if email_log else None,
                'call_status': call_task.status if call_task else None,
            }
        )

    return templates.TemplateResponse(
        'dashboard.html',
        {
            'request': request,
            'lead_rows': lead_rows,
            'leads': leads,
            'status_counts': status_counts,
            'won_leads': won_leads,
            'db_warning': db_warning,
        },
    )


@app.post('/api/leads/scrape')
def scrape_leads(payload: ScrapeRequest, db: Session = Depends(get_db)):
    query_key = normalize_query_key(payload.query)
    start_index = 0
    checkpoint = None
    if payload.resume_from_last:
        checkpoint = db.scalar(select(ScrapeCheckpoint).where(ScrapeCheckpoint.query_key == query_key))
        if checkpoint:
            start_index = checkpoint.last_offset

    try:
        scrape_result = scrape_google_maps_sync(
            payload.query,
            payload.max_results,
            start_index=start_index,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f'Scrape failed: {exc}',
        ) from exc
    service = LeadService(db)

    created = 0
    skipped_has_website = 0
    skipped_missing_phone = 0
    duplicates = 0

    for item in scrape_result.leads:
        _, result = service.create_or_skip(item, source_query=payload.query)
        if result == 'created':
            created += 1
        elif result == 'skipped_has_website':
            skipped_has_website += 1
        elif result == 'skipped_missing_phone':
            skipped_missing_phone += 1
        else:
            duplicates += 1

    if payload.resume_from_last:
        new_offset = start_index + scrape_result.consumed_count
        if checkpoint:
            checkpoint.last_offset = new_offset
        else:
            db.add(ScrapeCheckpoint(query_key=query_key, last_offset=new_offset))
        db.commit()

    return {
        'scraped_total': len(scrape_result.leads),
        'created': created,
        'skipped_has_website': skipped_has_website,
        'skipped_missing_phone': skipped_missing_phone,
        'duplicates': duplicates,
        'resume_from_last': payload.resume_from_last,
        'start_index': start_index,
        'next_start_index': start_index + scrape_result.consumed_count,
    }


@app.get('/api/leads')
def list_leads(db: Session = Depends(get_db)):
    rows = db.scalars(select(Lead).order_by(Lead.created_at.desc()).limit(1000)).all()
    return [
        {
            'id': r.id,
            'business_name': r.business_name,
            'phone': r.phone,
            'email': r.email,
            'website': r.website,
            'status': r.status,
            'address': r.address,
            'source_query': r.source_query,
            'created_at': r.created_at.isoformat(),
        }
        for r in rows
    ]


@app.get('/api/leads/export.csv')
def export_leads_csv(db: Session = Depends(get_db)):
    leads = db.scalars(select(Lead).order_by(Lead.created_at.desc())).all()
    lead_ids = [lead.id for lead in leads]

    latest_proposal_by_lead: dict[int, Proposal] = {}
    latest_email_log_by_lead: dict[int, OutreachLog] = {}
    latest_call_task_by_lead: dict[int, CallTask] = {}
    if lead_ids:
        proposals = db.scalars(
            select(Proposal)
            .where(Proposal.lead_id.in_(lead_ids))
            .order_by(Proposal.lead_id.asc(), Proposal.created_at.desc())
        ).all()
        for proposal in proposals:
            latest_proposal_by_lead.setdefault(proposal.lead_id, proposal)

        email_logs = db.scalars(
            select(OutreachLog)
            .where(OutreachLog.lead_id.in_(lead_ids))
            .where(OutreachLog.channel == 'email')
            .order_by(OutreachLog.lead_id.asc(), OutreachLog.created_at.desc())
        ).all()
        for email_log in email_logs:
            latest_email_log_by_lead.setdefault(email_log.lead_id, email_log)

        call_tasks = db.scalars(
            select(CallTask)
            .where(CallTask.lead_id.in_(lead_ids))
            .order_by(CallTask.lead_id.asc(), CallTask.created_at.desc())
        ).all()
        for call_task in call_tasks:
            latest_call_task_by_lead.setdefault(call_task.lead_id, call_task)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            'id',
            'business_name',
            'category',
            'address',
            'phone',
            'phone_normalized',
            'email',
            'website',
            'google_maps_url',
            'source_query',
            'status',
            'contacted',
            'proposal_pdf_url',
            'email_status',
            'email_details',
            'call_status',
            'notes',
            'created_at',
            'updated_at',
        ]
    )

    for lead in leads:
        proposal = latest_proposal_by_lead.get(lead.id)
        email_log = latest_email_log_by_lead.get(lead.id)
        call_task = latest_call_task_by_lead.get(lead.id)

        proposal_pdf_url = ''
        if proposal and proposal.pdf_path:
            proposal_pdf_url = f'/proposals/{Path(proposal.pdf_path).name}'

        writer.writerow(
            [
                lead.id,
                lead.business_name or '',
                lead.category or '',
                lead.address or '',
                lead.phone or '',
                lead.phone_normalized or '',
                lead.email or '',
                lead.website or '',
                lead.google_maps_url or '',
                lead.source_query or '',
                lead.status or '',
                'yes' if lead.contacted else 'no',
                proposal_pdf_url,
                email_log.result if email_log else '',
                email_log.details if email_log else '',
                call_task.status if call_task else '',
                lead.notes or '',
                lead.created_at.isoformat() if lead.created_at else '',
                lead.updated_at.isoformat() if lead.updated_at else '',
            ]
        )

    filename = f'leads_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    csv_content = output.getvalue()
    output.close()
    return Response(
        content=csv_content,
        media_type='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )


@app.post('/api/outreach/run')
def run_outreach(batch_size: int = 10, db: Session = Depends(get_db)):
    if batch_size < 1:
        raise HTTPException(status_code=400, detail='batch_size must be >= 1')
    return OutreachService(db).run_batch(batch_size=batch_size)


@app.post('/api/leads/{lead_id}/status')
def update_status(lead_id: int, payload: StatusUpdateRequest, db: Session = Depends(get_db)):
    lead = LeadService(db).set_status(lead_id, payload.status)
    if not lead:
        raise HTTPException(status_code=404, detail='Lead not found')
    return {'ok': True, 'lead_id': lead.id, 'status': lead.status}


@app.post('/api/leads/{lead_id}/call-outcome')
def set_call_outcome(lead_id: int, payload: CallOutcomeRequest, db: Session = Depends(get_db)):
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail='Lead not found')

    mapping = {
        'yes': 'interested',
        'no': 'lost',
        'later': 'follow_up',
    }
    lead.status = mapping.get(payload.outcome.lower(), lead.status)
    if payload.notes:
        lead.notes = (lead.notes or '') + f'\nCall note: {payload.notes}'
    db.commit()

    return {'ok': True, 'status': lead.status}


@app.get('/api/metrics')
def metrics(db: Session = Depends(get_db)):
    total = db.scalar(select(func.count(Lead.id))) or 0
    no_website = db.scalar(select(func.count(Lead.id)).where(Lead.website.is_(None))) or 0
    interested = db.scalar(select(func.count(Lead.id)).where(Lead.status == 'interested')) or 0
    won = db.scalar(select(func.count(Lead.id)).where(Lead.status == 'won')) or 0

    return {
        'total_leads': total,
        'no_website_leads': no_website,
        'interested_leads': interested,
        'won_leads': won,
    }
