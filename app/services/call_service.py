import json

import requests
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import CallTask, Lead, OutreachLog

settings = get_settings()


class CallService:
    def __init__(self, db: Session):
        self.db = db

    def build_call_script(self, lead: Lead) -> str:
        return (
            f'Hello, am I speaking with {lead.business_name}? '
            'I am calling because we help local businesses with no website get more customer calls. '
            'Can I share a quick website plan tailored for your business?'
        )

    def queue_call(self, lead: Lead) -> CallTask:
        task = CallTask(
            lead_id=lead.id,
            script_text=self.build_call_script(lead),
            status='pending',
        )
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return task

    def dispatch_pending_calls(self, limit: int = 10) -> int:
        tasks = (
            self.db.query(CallTask)
            .filter(CallTask.status == 'pending')
            .limit(limit)
            .all()
        )

        sent_count = 0
        for task in tasks:
            lead = self.db.get(Lead, task.lead_id)
            if not lead or not lead.phone_normalized:
                task.status = 'failed'
                task.provider_response = 'Missing lead or phone'
                continue

            if not settings.call_agent_webhook:
                # Free default mode: queue only. External call provider can poll this table.
                task.status = 'queued'
                task.provider_response = 'No webhook configured. Task queued only.'
                sent_count += 1
                continue

            try:
                payload = {
                    'lead_id': lead.id,
                    'business_name': lead.business_name,
                    'phone': lead.phone_normalized,
                    'script': task.script_text,
                }
                headers = {'Content-Type': 'application/json'}
                if settings.call_agent_token:
                    headers['Authorization'] = f'Bearer {settings.call_agent_token}'

                response = requests.post(
                    settings.call_agent_webhook,
                    headers=headers,
                    data=json.dumps(payload),
                    timeout=20,
                )
                response.raise_for_status()
                task.status = 'done'
                task.provider_response = response.text[:5000]
                task.provider_call_id = response.headers.get('x-call-id')
                sent_count += 1

                self.db.add(
                    OutreachLog(
                        lead_id=lead.id,
                        channel='call',
                        result='sent',
                        details=f'Call webhook accepted for {lead.phone_normalized}',
                    )
                )
            except Exception as exc:
                task.status = 'failed'
                task.provider_response = str(exc)
                self.db.add(
                    OutreachLog(
                        lead_id=lead.id,
                        channel='call',
                        result='failed',
                        details=str(exc),
                    )
                )

        self.db.commit()
        return sent_count
