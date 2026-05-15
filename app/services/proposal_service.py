from pathlib import Path
from textwrap import wrap

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.models import Lead


class ProposalService:
    def __init__(self, output_dir: str = 'storage/proposals'):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def create_proposal_text(self, lead: Lead) -> tuple[str, str]:
        title = f'Web Growth Proposal for {lead.business_name}'
        body = (
            f'Hello {lead.business_name} Team,\n\n'
            f'We noticed your business has strong local visibility but no website. '
            f'We can build a fast, mobile-friendly website that helps customers discover your services and contact you instantly.\n\n'
            f'What we propose:\n'
            f'- 5-page professional website tailored to your business category ({lead.category or "General"})\n'
            f'- WhatsApp + call buttons for immediate lead capture\n'
            f'- Google Maps and local SEO setup\n'
            f'- Basic analytics + contact form integration\n\n'
            f'Estimated timeline: 7-10 days\n'
            f'Estimated investment: INR 18,000 to INR 35,000 (based on exact scope)\n\n'
            f'If you are interested, reply YES and we will share a final scope and start date.\n\n'
            f'Thank you.'
        )
        return title, body

    def create_pdf(self, lead: Lead, title: str, body: str) -> str:
        safe_name = ''.join(c for c in lead.business_name if c.isalnum() or c in (' ', '_', '-')).strip().replace(' ', '_')
        filename = f'{lead.id}_{safe_name}.pdf'
        path = self.output_dir / filename

        pdf = canvas.Canvas(str(path), pagesize=A4)
        width, height = A4

        y = height - 50
        pdf.setFont('Helvetica-Bold', 16)
        pdf.drawString(50, y, title)

        y -= 30
        pdf.setFont('Helvetica', 11)
        for paragraph in body.split('\n'):
            lines = wrap(paragraph, 95) if paragraph else ['']
            for line in lines:
                if y < 60:
                    pdf.showPage()
                    y = height - 50
                    pdf.setFont('Helvetica', 11)
                pdf.drawString(50, y, line)
                y -= 16

        pdf.save()
        return str(path)
