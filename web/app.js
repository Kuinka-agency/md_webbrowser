const MAX_EVENT_ROWS = 50;
const EVENTS_POLL_INTERVAL_MS = 2000;
const EMBEDDING_DIM = 1536;
const WARNING_LABELS = {
  'canvas-heavy': 'Canvas Heavy',
  'video-heavy': 'Video Heavy',
  'sticky-chrome': 'Sticky Overlay',
};

function setupTabs() {
  const tabButtons = Array.from(document.querySelectorAll('[data-tab-target]'));
  const panels = new Map(
    Array.from(document.querySelectorAll('[data-tab-panel]')).map((panel) => [
      panel.dataset.tabPanel,
      panel,
    ]),
  );

  if (!tabButtons.length || !panels.size) {
    return;
  }

  const activate = (id) => {
    tabButtons.forEach((btn) => {
      const isActive = btn.dataset.tabTarget === id;
      btn.classList.toggle('active', isActive);
      btn.setAttribute('aria-selected', String(isActive));
    });
    panels.forEach((panel, key) => {
      panel.hidden = key !== id;
    });
  };

  tabButtons.forEach((button) => {
    button.addEventListener('click', () => activate(button.dataset.tabTarget));
  });

  activate(tabButtons[0].dataset.tabTarget);
}

function initSseBridge() {
  const root = document.querySelector('[data-stream-root]');
  const statusEl = document.getElementById('job-sse-status');
  if (!root || !statusEl) {
    return null;
  }
  const embeddingsPanel = initEmbeddingsPanel(root);
  const eventsPanel = initEventsPanel(root);

  const fieldMap = new Map();
  root.querySelectorAll('[data-sse-field]').forEach((el) => {
    fieldMap.set(el.dataset.sseField, el);
  });
  const warningListEl = root.querySelector('[data-warning-list]');
  const blocklistHitsEl = root.querySelector('[data-blocklist-hits]');

  const setStatus = (value, variant = 'info') => {
    statusEl.textContent = value;
    statusEl.dataset.variant = variant;
  };

  const updateField = (field, payload) => {
    const el = fieldMap.get(field);
    if (!el) {
      return;
    }
    switch (field) {
      case 'manifest':
        renderManifest(el, payload, { warningListEl, blocklistHitsEl });
        break;
      case 'raw':
        el.textContent = payload;
        break;
      case 'links':
        renderLinks(el, payload);
        break;
      case 'artifacts':
        renderArtifacts(el, payload);
        break;
      default:
        el.innerHTML = payload;
    }
  };

  const fetchTemplateJson = async (template, jobId) => {
    const target = buildTemplateUrl(template, jobId);
    const response = await fetch(target);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    return response.json();
  };

  const refreshLinks = async (jobId) => {
    if (!root) {
      return;
    }
    const template = root.dataset.linksTemplate || '/jobs/{job_id}/links.json';
    try {
      const data = await fetchTemplateJson(template, jobId);
      updateField('links', JSON.stringify(data));
    } catch (error) {
      console.error('Failed to refresh links', error);
    }
  };

  const refreshManifest = async (jobId) => {
    if (!root) {
      return;
    }
    const template = root.dataset.manifestTemplate || '/jobs/{job_id}/manifest.json';
    try {
      const data = await fetchTemplateJson(template, jobId);
      updateField('manifest', JSON.stringify(data));
    } catch (error) {
      if (!(error?.message || '').includes('404')) {
        console.error('Failed to refresh manifest', error);
      }
    }
  };

  let source = null;
  let currentJobId = root.dataset.jobId || 'demo';

  const connect = (jobId) => {
    if (source) {
      source.close();
    }
    const template = root.dataset.streamTemplate || '/jobs/{job_id}/stream';
    currentJobId = jobId || 'demo';
    const url = buildTemplateUrl(template, currentJobId);
    root.dataset.jobId = currentJobId;
    const jobField = document.getElementById('job-id');
    if (jobField) {
      jobField.value = currentJobId;
    }
    source = new EventSource(url);
    setStatus('Connecting…', 'pending');
    embeddingsPanel?.setJobId(currentJobId);
    eventsPanel?.connect(currentJobId);
    refreshManifest(currentJobId);
    refreshLinks(currentJobId);
    source.addEventListener('open', () => setStatus(`Connected (${currentJobId})`, 'success'));
    source.addEventListener('error', () => setStatus('Disconnected — retrying…', 'warning'));
    source.addEventListener('state', (event) => {
      updateField('state', event.data);
      const normalized = (event.data || '').trim().toUpperCase();
      if (normalized === 'DONE' || normalized === 'FAILED') {
        refreshManifest(currentJobId);
        refreshLinks(currentJobId);
      }
    });
    source.addEventListener('progress', (event) => updateField('progress', event.data));
    source.addEventListener('runtime', (event) => updateField('runtime', event.data));
    source.addEventListener('manifest', (event) => updateField('manifest', event.data));
    source.addEventListener('rendered', (event) => updateField('rendered', event.data));
    source.addEventListener('raw', (event) => updateField('raw', event.data));
    source.addEventListener('links', (event) => updateField('links', event.data));
    source.addEventListener('artifacts', (event) => updateField('artifacts', event.data));
    source.addEventListener('warnings', (event) => renderWarnings(warningListEl, event.data));
  };

  const defaultJob = root.dataset.jobId || 'demo';
  connect(defaultJob);

  window.addEventListener('beforeunload', () => {
    if (source) {
      source.close();
    }
    eventsPanel?.stop?.();
  });

  return { connect, refreshLinks };
}

function renderManifest(element, payload, { warningListEl, blocklistHitsEl }) {
  let formatted = payload;
  try {
    const parsed = JSON.parse(payload);
    formatted = JSON.stringify(parsed, null, 2);
    if (parsed?.warnings) {
      renderWarnings(warningListEl, parsed.warnings);
    }
    if (parsed?.blocklist_hits) {
      renderBlocklistHits(blocklistHitsEl, parsed.blocklist_hits);
    }
  } catch {
    // fall through
  }
  element.textContent = formatted;
}

function renderLinks(container, raw) {
  let rows;
  try {
    rows = JSON.parse(raw);
  } catch {
    container.innerHTML = `<p class="placeholder">Invalid links payload</p>`;
    return;
  }

  if (!Array.isArray(rows) || !rows.length) {
    container.innerHTML = `<p class="placeholder">No links yet.</p>`;
    return;
  }

  const header = ['text', 'href', 'source', 'delta'];
  const table = document.createElement('table');
  const thead = document.createElement('thead');
  const headRow = document.createElement('tr');
  header.forEach((label) => {
    const th = document.createElement('th');
    th.textContent = label.toUpperCase();
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);
  table.appendChild(thead);
  const tbody = document.createElement('tbody');
  rows.forEach((row) => {
    const tr = document.createElement('tr');
    header.forEach((key) => {
      const td = document.createElement('td');
      td.textContent = row[key] ?? '—';
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  container.innerHTML = '';
  container.appendChild(table);
}

function renderArtifacts(container, raw) {
  let rows;
  try {
    rows = JSON.parse(raw);
  } catch {
    container.innerHTML = `<li class="placeholder">Invalid artifact payload</li>`;
    return;
  }

  if (!Array.isArray(rows) || !rows.length) {
    container.innerHTML = `<li class="placeholder">No artifacts yet.</li>`;
    return;
  }

  container.innerHTML = '';
  rows.forEach((artifact) => {
    const li = document.createElement('li');
    const left = document.createElement('div');
    const idEl = document.createElement('strong');
    idEl.textContent = artifact.id ?? 'tile';
    const offsetEl = document.createElement('small');
    offsetEl.textContent = artifact.offset ?? '';
    left.append(idEl);
    left.append(document.createElement('br'));
    left.append(offsetEl);
    const right = document.createElement('div');
    right.textContent = artifact.sha ?? '';
    li.append(left, right);
    container.appendChild(li);
  });
}

function renderWarnings(container, payload) {
  if (!container) {
    return;
  }
  let warnings = payload;
  if (typeof payload === 'string') {
    try {
      warnings = JSON.parse(payload);
    } catch {
      warnings = null;
    }
  }
  container.innerHTML = '';
  if (!Array.isArray(warnings) || warnings.length === 0) {
    const span = document.createElement('span');
    span.className = 'warning-empty';
    span.textContent = 'None detected.';
    container.appendChild(span);
    return;
  }
  warnings.forEach((warning) => {
    const pill = document.createElement('div');
    pill.className = 'warning-pill';
    const code = document.createElement('span');
    code.className = 'warning-pill__code';
    code.textContent = WARNING_LABELS[warning.code] || warning.code;
    const meta = document.createElement('span');
    meta.className = 'warning-pill__meta';
    const count = warning.count ?? '?';
    const threshold = warning.threshold ?? '?';
    meta.textContent = `${count} hits (>= ${threshold})`;
    const message = document.createElement('span');
    message.textContent = warning.message || '';
    pill.append(code, meta, message);
    container.appendChild(pill);
  });
}

function renderBlocklistHits(container, payload) {
  if (!container) {
    return;
  }
  let hits = payload;
  if (typeof payload === 'string') {
    try {
      hits = JSON.parse(payload);
    } catch {
      hits = null;
    }
  }
  container.innerHTML = '';
  if (!hits || !Object.keys(hits).length) {
    const p = document.createElement('p');
    p.className = 'placeholder';
    p.textContent = 'No selectors matched during this run.';
    container.appendChild(p);
    return;
  }
  Object.entries(hits).forEach(([selector, count]) => {
    const row = document.createElement('div');
    row.className = 'blocklist-entry';
    const left = document.createElement('span');
    left.className = 'blocklist-entry__selector';
    left.textContent = selector;
    const right = document.createElement('strong');
    right.textContent = count.toString();
    row.append(left, right);
    container.appendChild(row);
  });
}

function initEmbeddingsPanel(streamRoot) {
  const panel = document.querySelector('[data-embeddings-panel]');
  if (!panel) {
    return null;
  }
  const vectorInput = panel.querySelector('[data-embeddings-vector]');
  const topKInput = panel.querySelector('[data-embeddings-topk]');
  const runButton = panel.querySelector('[data-embeddings-run]');
  const demoButton = panel.querySelector('[data-embeddings-demo]');
  const statusEl = panel.querySelector('[data-embeddings-status]');
  const resultsEl = panel.querySelector('[data-embeddings-results]');
  let currentJobId = streamRoot?.dataset.jobId || 'demo';

  const setStatus = (text) => {
    if (statusEl) {
      statusEl.textContent = text;
    }
  };

  const renderResults = (matches, total) => {
    if (!resultsEl) {
      return;
    }
    resultsEl.innerHTML = '';
    if (!matches?.length) {
      const p = document.createElement('p');
      p.className = 'placeholder';
      p.textContent = total ? 'No matches for this vector.' : 'No embeddings available for this job yet.';
      resultsEl.appendChild(p);
      return;
    }
    const table = document.createElement('table');
    const thead = document.createElement('thead');
    const headerRow = document.createElement('tr');
    ['section', 'tiles', 'similarity', 'distance'].forEach((title) => {
      const th = document.createElement('th');
      th.textContent = title.toUpperCase();
      headerRow.appendChild(th);
    });
    thead.appendChild(headerRow);
    table.appendChild(thead);
    const tbody = document.createElement('tbody');
    matches.forEach((match) => {
      const row = document.createElement('tr');
      const section = document.createElement('td');
      section.textContent = match.section_id;
      const tiles = document.createElement('td');
      const start = match.tile_start ?? '—';
      const end = match.tile_end ?? '—';
      tiles.textContent = `${start} → ${end}`;
      const similarity = document.createElement('td');
      similarity.textContent = match.similarity.toFixed(4);
      const distance = document.createElement('td');
      distance.textContent = match.distance.toFixed(4);
      row.append(section, tiles, similarity, distance);
      tbody.appendChild(row);
    });
    table.appendChild(tbody);
    resultsEl.appendChild(table);
  };

  const parseVector = () => {
    if (!vectorInput) {
      throw new Error('Vector input not available');
    }
    const raw = vectorInput.value.trim();
    if (!raw) {
      throw new Error('Provide a JSON array with 1,536 numbers.');
    }
    let parsed;
    try {
      parsed = JSON.parse(raw);
    } catch {
      throw new Error('Vector must be valid JSON.');
    }
    if (!Array.isArray(parsed) || parsed.length !== EMBEDDING_DIM) {
      throw new Error(`Vector must contain exactly ${EMBEDDING_DIM} numbers.`);
    }
    return parsed;
  };

  const runSearch = async () => {
    try {
      setStatus('Searching…');
      const vector = parseVector();
      const topK = Math.min(
        50,
        Math.max(1, parseInt(topKInput?.value || '5', 10) || 5),
      );
      const jobId = currentJobId || 'demo';
      const response = await fetch(`/jobs/${encodeURIComponent(jobId)}/embeddings/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ vector, top_k: topK }),
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `HTTP ${response.status}`);
      }
      const data = await response.json();
      renderResults(data.matches, data.total_sections);
      setStatus(`Found ${data.matches.length} of ${data.total_sections} sections for job ${jobId}.`);
    } catch (error) {
      console.error('Embeddings search failed', error);
      setStatus(error.message || 'Search failed');
    }
  };

  const buildDemoVector = () => {
    const vec = Array(EMBEDDING_DIM).fill(0);
    vec[0] = 1;
    vec[1] = 0.5;
    return vec;
  };

  runButton?.addEventListener('click', runSearch);
  demoButton?.addEventListener('click', () => {
    if (!vectorInput) {
      return;
    }
    vectorInput.value = JSON.stringify(buildDemoVector());
    setStatus('Demo vector loaded. Adjust as needed, then click Search.');
  });

  const setJobId = (jobId) => {
    currentJobId = jobId || 'demo';
    setStatus(`Ready to query embeddings for job ${currentJobId}.`);
  };

  setJobId(currentJobId);
  return { setJobId };
}

function initStreamControls(sse) {
  const runButton = document.getElementById('run-job');
  const urlInput = document.getElementById('job-url');
  const jobInput = document.getElementById('job-id');
  const profileSelect = document.getElementById('profile');
  const ocrSelect = document.getElementById('ocr-policy');
  const root = document.querySelector('[data-stream-root]');
  const statusEl = document.querySelector('[data-run-status]');
  if (!runButton || !jobInput || !root || !sse?.connect) {
    return;
  }

  const setRunStatus = (text, variant = 'info') => {
    if (!statusEl) return;
    statusEl.textContent = text;
    statusEl.dataset.variant = variant;
  };

  const submitJob = async () => {
    const urlValue = urlInput?.value.trim();
    if (!urlValue) {
      const existingJob = jobInput.value.trim();
      if (existingJob) {
        setRunStatus(`Attaching to job ${existingJob}…`);
        sse.connect(existingJob);
      } else {
        setRunStatus('Provide a URL or job id first.', 'error');
      }
      return;
    }

    const payload = { url: urlValue };
    if (profileSelect?.value && profileSelect.value !== 'default') {
      payload.profile_id = profileSelect.value;
    }
    if (ocrSelect?.value) {
      payload.ocr_policy = ocrSelect.value;
    }

    runButton.disabled = true;
    setRunStatus('Submitting capture job…');
    try {
      const response = await fetch('/jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `HTTP ${response.status}`);
      }
      const job = await response.json();
      if (job?.id) {
        jobInput.value = job.id;
        if (root) {
          root.dataset.jobId = job.id;
        }
        setRunStatus(`Job ${job.id} submitted. Connecting to stream…`, 'success');
        sse.connect(job.id);
      } else {
        setRunStatus('Submission succeeded but response missing job id.', 'error');
      }
    } catch (error) {
      console.error('Job submission failed', error);
      setRunStatus(error.message || 'Failed to submit job', 'error');
    } finally {
      runButton.disabled = false;
    }
  };

  runButton.addEventListener('click', submitJob);

  const refreshButton = document.querySelector('[data-links-refresh]'); 
  if (refreshButton) {
    refreshButton.addEventListener('click', async () => {
      const template = root.dataset.linksTemplate || '/jobs/{job_id}/links.json';
      const jobId = root.dataset.jobId || jobInput.value.trim() || 'demo';
      const url = template.replace('{job_id}', jobId);
      try {
        const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        renderLinks(root.querySelector('[data-sse-field=\"links\"]'), JSON.stringify(data));
      } catch (error) {
        console.error('Failed to refresh links', error);
      }
    });
  }
}

function init() {
  setupTabs();
  const sse = initSseBridge();
  initStreamControls(sse);
}

init();
