const $ = (selector) => document.querySelector(selector);
const departments = ['Billing', 'Technical Support', 'Account Support', 'Sales', 'General Support'];
const intents = ['Refund Request', 'Payment Problem', 'Bug Report', 'Login Problem', 'Account Change', 'Cancellation', 'Feature Request', 'Product Question', 'Sales Inquiry', 'Other'];
const urgencies = ['Low', 'Medium', 'High', 'Critical'];
const state = { view: 'overview', tickets: [], analytics: null, evaluation: null, selected: null, mode: null, reelScene: 0, page: 0 };
const labels = { INCOMING: 'Incoming', AUTO_ROUTED: 'Auto-routed', NEEDS_REVIEW: 'Needs review', APPROVED: 'Approved', CORRECTED: 'Corrected' };
const pageInfo = {
  overview: ['YOUR WORKSPACE AT A GLANCE', 'Ticket activity', 'See what needs attention and where every request is headed.', 'Overview'],
  incoming: ['THE INBOX', 'Incoming tickets', 'New requests waiting for a routing decision.', 'Incoming tickets'],
  routed: ['CONFIDENT DECISIONS', 'Auto-routed tickets', 'Tickets assigned by the confidence gate.', 'Auto-routed'],
  review: ['HUMAN-IN-THE-LOOP', 'Human review queue', 'Uncertain and high-impact cases stay with your team.', 'Human review'],
  evaluation: ['MEASURE WHAT MATTERS', 'Evaluation dashboard', 'See how predictions compare with reviewed or synthetic labels.', 'Evaluation'],
};
function safe(value) { return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch])); }
function percent(value) { return value == null ? '—' : Math.round(value * 100) + '%'; }
function date(value) { return value ? new Date(value).toLocaleDateString('en-US', {month:'short',day:'numeric'}) : '—'; }
function toast(message) { const node = $('#toast'); node.textContent = message; node.classList.add('show'); clearTimeout(toast.timer); toast.timer = setTimeout(() => node.classList.remove('show'), 3500); }
async function api(path, options = {}) {
  const response = await fetch(path, {headers: {'Content-Type':'application/json'}, ...options});
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || `Request failed (${response.status})`);
  return body;
}
async function refresh() {
  try {
    const [tickets, analytics, evaluation, health] = await Promise.all([
      api('/api/tickets?limit=500'), api('/api/analytics'), api('/api/evaluation'), api('/api/health')
    ]);
    Object.assign(state, {tickets, analytics, evaluation, mode: health.mode});
    render();
  } catch (error) { toast(error.message); }
}
function render() {
  $('#mode-pill').textContent = state.mode === 'demo' ? 'Demo simulation' : 'Laya · CUDA';
  const counts = state.analytics?.statuses || {};
  $('#stat-total').textContent = state.analytics?.total ?? '—';
  $('#stat-routed').textContent = counts.AUTO_ROUTED || 0;
  $('#stat-review').textContent = counts.NEEDS_REVIEW || 0;
  $('#stat-confidence').textContent = state.analytics?.classified ? percent(state.analytics.average_confidence) : '—';
  $('#nav-incoming').textContent = counts.INCOMING || 0;
  $('#nav-review').textContent = counts.NEEDS_REVIEW || 0;
  renderRecent(); renderBars(); renderTable(); renderEvaluation(); renderView();
}
function renderView() {
  const [kicker, title, desc, crumb] = pageInfo[state.view];
  $('#section-kicker').textContent = kicker;
  $('#section-title').innerHTML = safe(title) + ' <span class="heading-spark">✦</span>';
  $('#section-desc').textContent = desc;
  $('#breadcrumb').textContent = crumb;
  $('#hero').hidden = state.view !== 'overview';
  $('#overview-grid').hidden = state.view !== 'overview';
  $('#evaluation-panel').hidden = state.view !== 'evaluation';
  $('#tickets-panel').hidden = state.view === 'evaluation';
  $('#stats').hidden = state.view === 'evaluation';
  $('#table-title').textContent = state.view === 'overview' ? 'All tickets' : title;
  $('#table-subtitle').textContent = state.view === 'overview' ? 'A clear view of every request' : desc;
  document.querySelectorAll('.nav-link').forEach(link => link.classList.toggle('active', link.dataset.view === state.view));
  if (state.view === 'incoming') $('#status-filter').value = 'INCOMING';
  if (state.view === 'routed') $('#status-filter').value = 'AUTO_ROUTED';
  if (state.view === 'review') $('#status-filter').value = 'NEEDS_REVIEW';
}
function renderRecent() {
  const list = state.tickets.slice(0, 4);
  $('#recent-list').innerHTML = list.length ? list.map(t => `<button class="recent-item" data-ticket="${safe(t.id)}"><span class="recent-icon ${t.priority === 'P1' ? 'critical' : ''}">${t.priority === 'P1' ? '!' : '✉'}</span><span class="recent-info"><strong>${safe(t.subject)}</strong><small>${safe(t.id)} · ${safe(t.customer_tier)} customer</small></span><span class="mini-status ${safe(t.status)}">${labels[t.status] || safe(t.status)}</span><span class="recent-time">${date(t.created_at)}</span></button>`).join('') : '<div class="empty">No tickets yet.</div>';
}
function renderBars() {
  const data = state.analytics?.departments || {};
  const max = Math.max(1, ...Object.values(data));
  $('#department-bars').innerHTML = departments.map(name => `<div class="bar-line"><span>${safe(name)}</span><div class="bar-track"><div class="bar-fill" style="width:${Math.max(0,(data[name] || 0) / max * 100)}%"></div></div><b>${data[name] || 0}</b></div>`).join('');
}
function visibleTickets() {
  const viewStatus = {incoming:'INCOMING',routed:'AUTO_ROUTED',review:'NEEDS_REVIEW'}[state.view];
  const status = viewStatus || $('#status-filter').value;
  const query = $('#search-input').value.trim().toLowerCase();
  return state.tickets.filter(t => (!status || t.status === status) && (!query || [t.id,t.subject,t.body,t.customer_id].some(x => (x || '').toLowerCase().includes(query))));
}
function renderTable() {
  const items = visibleTickets();
  const pages = Math.max(1, Math.ceil(items.length / 10));
  state.page = Math.min(state.page, pages - 1);
  const shown = items.slice(state.page * 10, state.page * 10 + 10);
  $('#ticket-table').innerHTML = shown.map(t => `<tr><td><strong class="ticket-id">${safe(t.id)}</strong><strong>${safe(t.subject)}</strong></td><td>${safe(t.customer_id || 'New customer')}</td><td>${safe(t.department || 'Unclassified')}</td><td><span class="priority ${safe(t.priority || '')}">${safe(t.priority || '—')}</span></td><td><span class="mini-status ${safe(t.status)}">${labels[t.status] || safe(t.status)}</span></td><td>${date(t.created_at)}</td><td><button class="row-open" data-ticket="${safe(t.id)}" aria-label="Open ${safe(t.id)}">→</button></td></tr>`).join('') || '<tr><td colspan="7" class="empty">No tickets match this view.</td></tr>';
  $('#table-footer').innerHTML = `<span>Showing ${shown.length ? state.page * 10 + 1 : 0}–${state.page * 10 + shown.length} of ${items.length} tickets</span><span class="page-controls"><button id="page-prev" ${state.page === 0 ? 'disabled' : ''}>←</button><b>${state.page + 1} / ${pages}</b><button id="page-next" ${state.page >= pages - 1 ? 'disabled' : ''}>→</button></span>`;
  $('#page-prev').onclick = () => { state.page--; renderTable(); };
  $('#page-next').onclick = () => { state.page++; renderTable(); };
}
function renderEvaluation() {
  const e = state.evaluation;
  if (!e?.evaluated) { $('#evaluation-content').innerHTML = '<div class="empty">No measured predictions yet. Classify labeled sample tickets to see metrics.</div>'; return; }
  const metrics = [['Department accuracy',e.department_accuracy],['Intent accuracy',e.intent_accuracy],['Urgency accuracy',e.urgency_accuracy],['Wrong auto-route rate',e.wrong_auto_route_rate]];
  const matrixLabels = Object.keys(e.confusion_matrix);
  $('#evaluation-content').innerHTML = `<div class="eval-grid">${metrics.map(([name,value]) => `<div class="eval-card"><small>${safe(name)}</small><strong>${percent(value)}</strong></div>`).join('')}</div><div class="eval-detail"><div><h4>Signal quality</h4><table class="metrics-table"><thead><tr><th>DETECTION</th><th>PRECISION</th><th>RECALL</th><th>F1</th></tr></thead><tbody>${['refund','churn'].map(name => `<tr><td>${name === 'refund' ? 'Refund request' : 'Churn risk'}</td><td>${percent(e[name].precision)}</td><td>${percent(e[name].recall)}</td><td>${percent(e[name].f1)}</td></tr>`).join('')}</tbody></table><p>${e.evaluated} evaluated · Auto-route ${percent(e.auto_route_rate)} · Human review ${percent(e.human_review_rate)} · Avg. confidence ${percent(e.average_department_confidence)}</p><p>Prediction sources: ${Object.entries(e.prediction_sources).map(([k,v]) => `${safe(k)} ${v}`).join(', ')}. Ground truth: ${Object.entries(e.truth_origins).map(([k,v]) => `${safe(k)} ${v}`).join(', ')}.</p></div><div><h4>Department confusion matrix</h4><div class="matrix"><table><thead><tr><th>ACTUAL ↓ / PREDICTED →</th>${matrixLabels.map(x => `<th>${safe(x.split(' ')[0])}</th>`).join('')}</tr></thead><tbody>${matrixLabels.map(actual => `<tr><td>${safe(actual)}</td>${matrixLabels.map(pred => `<td class="${actual === pred ? 'diag' : ''}">${e.confusion_matrix[actual][pred]}</td>`).join('')}</tr>`).join('')}</tbody></table></div></div></div>`;
}
function setView(view) { state.view = view; state.page = 0; if (view === 'overview' || view === 'evaluation') $('#status-filter').value = ''; render(); window.scrollTo({top:0,behavior:'smooth'}); }
async function openTicket(id) {
  try { state.selected = await api(`/api/tickets/${encodeURIComponent(id)}`); renderDetail(); $('#drawer-backdrop').hidden = false; $('#drawer').classList.add('open'); $('#drawer').setAttribute('aria-hidden','false'); }
  catch (error) { toast(error.message); }
}
function closeDrawer() { $('#drawer').classList.remove('open'); $('#drawer').setAttribute('aria-hidden','true'); $('#drawer-backdrop').hidden = true; }
function metricRow(label, value, confidence) { return `<div class="detail-row"><span>${safe(label)}</span><strong>${safe(value)}${confidence == null ? '' : ` · ${percent(confidence)}`}</strong></div>`; }
function renderDetail() {
  const t = state.selected; if (!t) return;
  $('#detail-id').textContent = t.id;
  const classified = Boolean(t.department);
  const source = t.source === 'simulation' ? 'Demo simulation · deterministic preview, not model inference' : t.source === 'laya' ? `Laya model · ${t.model} · CUDA` : 'Awaiting classification';
  const gateText = {auto_route:'High confidence: routed automatically.',human_confirmation:'Medium confidence: human confirmation required.',manual_triage:'Low confidence: manual triage required.',critical_escalation:'Critical priority: senior human review required.',senior_confirmation:'Escalation signal: senior confirmation required.',human_approved:'Human approved this prediction.',human_corrected:'Human correction saved as ground truth.'}[t.gate] || 'Awaiting a routing decision.';
  $('#drawer-body').innerHTML = `<h3 class="detail-subject">${safe(t.subject)}</h3><div class="detail-meta"><span class="detail-chip">${safe(labels[t.status] || t.status)}</span><span class="detail-chip">${safe(t.customer_tier)}</span><span class="detail-chip">${safe(t.source_channel || 'Web')}</span></div><section class="detail-section"><h3>CUSTOMER MESSAGE</h3><p class="customer-message">${safe(t.body)}</p></section><section class="detail-section"><h3>${state.mode === 'demo' ? 'DEMO TRIAGE' : 'AI TRIAGE'}</h3>${classified ? `${metricRow('Department',t.department,t.department_confidence)}<div class="confidence-meter"><span style="width:${Math.round(t.department_confidence*100)}%"></span></div>${metricRow('Intent',t.intent,t.intent_confidence)}${metricRow('Urgency',t.urgency,t.urgency_confidence)}${metricRow('Frustration',['Neutral','Mild','Frustrated','High'][t.frustration],t.frustration_confidence)}${metricRow('Refund requested',percent(t.refund_probability))}${metricRow('Churn risk',percent(t.churn_probability))}${metricRow('Human escalation',percent(t.escalation_probability))}` : '<p class="source-note">Classify this ticket to see a decision.</p>'}<p class="source-note">${safe(source)}</p></section><section class="detail-section"><h3>ROUTING DECISION</h3><div class="gate-card"><strong>${safe(t.queue || 'Not yet assigned')} ${t.priority ? '· ' + safe(t.priority) : ''}</strong><p>${safe(gateText)}</p></div><div class="detail-actions"><button class="button button-primary" id="detail-classify">${classified ? (state.mode === 'demo' ? 'Re-run simulation →' : 'Reclassify with Laya →') : (state.mode === 'demo' ? 'Simulate routing →' : 'Classify ticket →')}</button>${classified ? '<button class="button button-subtle" id="detail-approve">Approve</button><button class="button button-subtle" id="detail-correct">Correct</button>' : ''}</div><p class="source-note">Tags: ${t.tags.length ? t.tags.map(safe).join(' · ') : 'None'}<br>Classification recommends routing only. Refunds, cancellation, and account changes require separate human action.</p></section>`;
  $('#detail-classify').onclick = () => classify(t.id);
  if (classified) { $('#detail-approve').onclick = () => approve(t.id); $('#detail-correct').onclick = () => openCorrection(t); }
}
async function classify(id) {
  const button = $('#detail-classify'); if (button) { button.disabled = true; button.textContent = 'Classifying…'; }
  try { state.selected = await api(`/api/tickets/${encodeURIComponent(id)}/classify`, {method:'POST'}); await refresh(); renderDetail(); toast(state.mode === 'demo' ? 'Demo simulation routed this ticket.' : 'Laya classified and routed this ticket.'); }
  catch (error) { toast(error.message); if (button) { button.disabled = false; button.textContent = 'Try again →'; } }
}
async function approve(id) {
  try { state.selected = await api(`/api/tickets/${encodeURIComponent(id)}/approve`, {method:'POST'}); await refresh(); renderDetail(); toast('Prediction approved and recorded.'); }
  catch (error) { toast(error.message); }
}
function fillSelect(selector, values, current) { $(selector).innerHTML = values.map(x => `<option ${x===current?'selected':''}>${safe(x)}</option>`).join(''); }
function openCorrection(t) {
  fillSelect('#correct-department',departments,t.department); fillSelect('#correct-intent',intents,t.intent); fillSelect('#correct-urgency',urgencies,t.urgency);
  const f = $('#correct-form'); f.elements.refund.checked = t.refund_probability >= .8; f.elements.churn.checked = t.churn_probability >= .8; f.elements.escalation.checked = t.escalation_probability >= .85;
  $('#correct-dialog').showModal();
}
function openCreate() { $('#create-dialog').showModal(); }
const reelScenes = [
  {id:'TCK-0001',caption:'01 / Duplicate charge → Billing'},
  {id:'TCK-0021',caption:'02 / Production outage → P1 review'},
  {id:'TCK-0012',caption:'03 / “No refund” → context matters'},
  {id:'TCK-0100',caption:'04 / Unclear request → human review'},
  {view:'evaluation',caption:'05 / Measure every decision'},
];
async function nextReelScene() {
  const scene = reelScenes[state.reelScene % reelScenes.length]; state.reelScene++;
  $('#reel-controls span').textContent = scene.caption;
  if (scene.view) { closeDrawer(); setView(scene.view); return; }
  setView('overview'); await openTicket(scene.id); if (state.selected && !state.selected.department) await classify(scene.id);
}
function startReel() { document.body.classList.add('reel-mode'); $('#reel-controls').hidden = false; state.reelScene = 0; nextReelScene(); }
function exitReel() { document.body.classList.remove('reel-mode'); $('#reel-controls').hidden = true; closeDrawer(); setView('overview'); }
document.querySelectorAll('.nav-link').forEach(node => node.onclick = () => setView(node.dataset.view));
document.querySelectorAll('[data-goto]').forEach(node => node.onclick = () => setView(node.dataset.goto));
document.querySelectorAll('#open-create,#hero-create,#open-create-side').forEach(node => node.onclick = openCreate);
$('#hero-demo').onclick = startReel;
$('#reel-next').onclick = nextReelScene; $('#reel-exit').onclick = exitReel;
$('#refresh-button').onclick = refresh;
$('#search-input').oninput = () => { state.page = 0; renderTable(); };
$('#status-filter').onchange = () => { state.page = 0; renderTable(); };
$('#recent-list').onclick = event => { const node = event.target.closest('[data-ticket]'); if (node) openTicket(node.dataset.ticket); };
$('#ticket-table').onclick = event => { const node = event.target.closest('[data-ticket]'); if (node) openTicket(node.dataset.ticket); };
$('#close-drawer').onclick = closeDrawer; $('#drawer-backdrop').onclick = closeDrawer;
$('#close-create').onclick = $('#cancel-create').onclick = () => $('#create-dialog').close();
$('#close-correct').onclick = $('#cancel-correct').onclick = () => $('#correct-dialog').close();
$('#create-form').onsubmit = async event => {
  event.preventDefault(); const form = event.currentTarget; const data = Object.fromEntries(new FormData(form));
  try { const ticket = await api('/api/tickets',{method:'POST',body:JSON.stringify(data)}); $('#create-dialog').close(); form.reset(); await refresh(); await openTicket(ticket.id); await classify(ticket.id); }
  catch (error) { toast(error.message); }
};
$('#correct-form').onsubmit = async event => {
  event.preventDefault(); const form = event.currentTarget; const payload = {department:form.elements.department.value,intent:form.elements.intent.value,urgency:form.elements.urgency.value,refund:form.elements.refund.checked,churn:form.elements.churn.checked,escalation:form.elements.escalation.checked};
  try { state.selected = await api(`/api/tickets/${encodeURIComponent(state.selected.id)}/correct`,{method:'POST',body:JSON.stringify(payload)}); $('#correct-dialog').close(); await refresh(); renderDetail(); toast('Human correction saved as ground truth.'); }
  catch (error) { toast(error.message); }
};
document.addEventListener('keydown', event => { if (event.key === 'Escape') closeDrawer(); });
refresh().then(() => { if (new URLSearchParams(location.search).has('reels')) startReel(); });
