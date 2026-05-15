from sqlalchemy.orm import Session

from app.models import OutreachLog, Proposal
from app.services.call_service import CallService
from app.services.email_service import EmailService
from app.services.lead_service import LeadService
from app.services.proposal_service import ProposalService


class OutreachService:
    def __init__(self, db: Session):
        self.db = db
        self.lead_service = LeadService(db)
        self.email_service = EmailService()
        self.proposal_service = ProposalService()
        self.call_service = CallService(db)

    def run_batch(self, batch_size: int = 10) -> dict:
        leads = self.lead_service.get_pending_for_outreach(limit=batch_size)
        email_sent = 0
        call_queued = 0

        for lead in leads:
            title, body = self.proposal_service.create_proposal_text(lead)
            pdf_path = self.proposal_service.create_pdf(lead, title, body)

            proposal = Proposal(
                lead_id=lead.id,
                title=title,
                body=body,
                pdf_path=pdf_path,
            )
            self.db.add(proposal)

            ok, result = self.email_service.send_proposal_email(
                lead=lead,
                subject=title,
                body=body,
                pdf_path=pdf_path,
            )
            if ok:
                proposal.sent_via_email = True
                lead.contacted = True
                lead.status = 'contacted'
                email_sent += 1

            self.db.add(
                OutreachLog(
                    lead_id=lead.id,
                    channel='email',
                    result='sent' if ok else 'failed',
                    details=result,
                )
            )

            call_task = self.call_service.queue_call(lead)
            if call_task:
                call_queued += 1

        self.db.commit()

        dispatched = self.call_service.dispatch_pending_calls(limit=batch_size)

        return {
            'picked_leads': len(leads),
            'emails_sent': email_sent,
            'calls_queued_or_sent': call_queued,
            'calls_dispatched_now': dispatched,
        }
