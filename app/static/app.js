const resultBox = document.getElementById('resultBox');

function showResult(ok, text) {
  resultBox.classList.remove('d-none', 'alert-success', 'alert-danger');
  resultBox.classList.add(ok ? 'alert-success' : 'alert-danger');
  resultBox.textContent = text;
}

function parseMaybeJson(text) {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function summarizeErrorResponse(statusCode, rawText, detailText) {
  const lowerRaw = (rawText || '').toLowerCase();
  const lowerDetail = (detailText || '').toLowerCase();
  if (lowerRaw.includes('error code 520') || lowerRaw.includes('cloudflare ray id') || lowerDetail.includes('error code 520')) {
    return 'Host crashed or returned invalid response (Cloudflare 520). Open Render Logs, restart service, and reduce scrape size (try 5-10).';
  }
  if (lowerDetail.includes('executable doesn') && lowerDetail.includes('headless_shell')) {
    return 'Playwright browser binary missing on host. Rebuild with browser install command and PLAYWRIGHT_BROWSERS_PATH.';
  }
  if (detailText) return detailText;
  if (statusCode) return `HTTP ${statusCode}`;
  return 'Unknown server error';
}

document.getElementById('scrapeForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const query = document.getElementById('query').value.trim();
  const maxResults = Number(document.getElementById('maxResults').value || 20);
  const resumeFromLast = document.getElementById('resumeFromLast').checked;

  try {
    const res = await fetch('/api/leads/scrape', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, max_results: maxResults, resume_from_last: resumeFromLast })
    });
    const raw = await res.text();
    const data = parseMaybeJson(raw);
    if (!res.ok) {
      const msg = summarizeErrorResponse(res.status, raw, data?.detail);
      throw new Error(msg);
    }
    if (!data) {
      throw new Error('Server returned non-JSON response.');
    }
    const modeText = data.resume_from_last
      ? `Resume ON (start ${data.start_index}, next ${data.next_start_index})`
      : 'Resume OFF (started from beginning)';
    showResult(true, `Scrape done. Created ${data.created}, duplicates ${data.duplicates}, skipped(has website) ${data.skipped_has_website}, skipped(no phone) ${data.skipped_missing_phone}. ${modeText}. Refresh page to view.`);
  } catch (err) {
    showResult(false, `Scrape failed: ${err.message}`);
  }
});

document.getElementById('outreachBtn').addEventListener('click', async () => {
  const batchSize = Number(document.getElementById('outreachBatchSize').value || 10);
  if (!Number.isFinite(batchSize) || batchSize < 1) {
    showResult(false, 'Outreach failed: batch size must be 1 or more.');
    return;
  }
  try {
    const res = await fetch(`/api/outreach/run?batch_size=${batchSize}`, { method: 'POST' });
    const raw = await res.text();
    const data = parseMaybeJson(raw);
    if (!res.ok) {
      const msg = summarizeErrorResponse(res.status, raw, data?.detail);
      throw new Error(msg);
    }
    if (!data) {
      throw new Error('Server returned non-JSON response.');
    }
    showResult(true, `Outreach done. Picked ${data.picked_leads}, emails sent ${data.emails_sent}, calls queued/sent ${data.calls_queued_or_sent}, calls dispatched now ${data.calls_dispatched_now}.`);
  } catch (err) {
    showResult(false, `Outreach failed: ${err.message}`);
  }
});
