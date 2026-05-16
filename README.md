# Lead Engine (Free Tools + MySQL or Postgres)

This project gives you an end-to-end MVP for:
- collecting leads from Google Maps searches,
- keeping only leads with **no website** and **valid phone**,
- storing data with duplicate protection,
- generating personalized proposal PDFs,
- sending proposal emails automatically,
- queuing/dispatching call tasks to a calling agent webhook,
- tracking lead status in a dashboard.

## Important note
Google Maps scraping can break when Google changes UI and may have legal/policy restrictions. Use responsibly and follow local laws and platform terms.

## Stack
- Backend: FastAPI
- Database: MySQL (XAMPP) or Postgres (Render)
- Scraper: Playwright (Chromium)
- PDF: ReportLab
- Email: SMTP (Gmail app password supported)
- Dashboard: Jinja2 + Bootstrap

## 1) Choose database mode
### Option A: Local MySQL (XAMPP)
1. Start **Apache** and **MySQL** in XAMPP Control Panel.
2. Ensure MySQL credentials are known (default often `root` with empty password).

### Option B: Render Postgres
1. Create a Postgres instance in Render.
2. Copy the **External Database URL**.
3. Set `DATABASE_URL` in `.env` (or Render env vars).
4. When `DATABASE_URL` is set, MySQL variables are ignored.

## 2) Setup project
```powershell
cd D:\claude
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium
Copy-Item .env.example .env
```

Edit `.env` with your database and SMTP credentials.

## 3) Create database and start app
```powershell
python scripts\create_database.py
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Note:
- For MySQL mode, `create_database.py` creates DB if missing.
- For Postgres mode (`DATABASE_URL` set), it skips create step automatically.
- For Render deployments using Playwright, prefer default browser cache path
  and use build command: `pip install -r requirements.txt && python -m playwright install --only-shell chromium`.

Open: http://127.0.0.1:8000

## 4) Workflow
1. In dashboard, run scrape query (example: `salon in pune`).
2. App inserts only leads with:
- website = empty
- phone = valid normalized phone
3. Optional: enable **Resume from last checked result** in scrape section:
- ON + same keyword: starts from previous offset
- ON + new keyword: starts from beginning (no previous checkpoint)
- OFF: always starts from beginning
3. Run outreach batch.
4. System creates proposal PDF per lead.
5. Email is sent when lead email exists and SMTP is configured.
6. Call tasks are queued and optionally dispatched to `CALL_AGENT_WEBHOOK`.
7. Update outcomes (`interested`, `won`, etc.) via API.

## API Quick Use
### Scrape
```bash
POST /api/leads/scrape
{
  "query": "dentist in delhi",
  "max_results": 20
}
```

### Run outreach
```bash
POST /api/outreach/run?batch_size=10
```

### Update status
```bash
POST /api/leads/{lead_id}/status
{
  "status": "won"
}
```

### Call outcome
```bash
POST /api/leads/{lead_id}/call-outcome
{
  "outcome": "yes",
  "notes": "Asked for detailed quote"
}
```

## Duplicate protection
- Soft dedupe before insert on:
- normalized phone
- email
- Google Maps URL
- DB unique constraint on `google_maps_url`

## Free-calling integration model
`CALL_AGENT_WEBHOOK` is optional.
- If empty: calls are stored and marked queued.
- If set: app posts call tasks to your agent endpoint.

You can connect a free self-hosted stack (for example: n8n + Asterisk/Freeswitch/SIP) to consume these tasks.

## Files
- `app/main.py` - API + dashboard routes
- `app/models.py` - SQLAlchemy schema
- `app/services/maps_scraper.py` - Google Maps lead collection
- `app/services/outreach_service.py` - proposal/email/call workflow
- `app/services/proposal_service.py` - PDF generation
- `scripts/create_database.py` - DB creation
