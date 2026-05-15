/* ====================================================================
   KiRouter app glue (Stage 3).
   - Polls /api/health, /api/info, and (when routing) /api/route/status.
   - Drives the Auto-route button: POST /api/route, poll, show progress,
     fetch /api/result, render previewed result, prompt accept/discard.
   - Drives the DRC button: POST /api/drc, list violations, mark canvas.
   ==================================================================== */

const $ = (sel) => document.querySelector(sel);

const els = {
  canvas:        $('#board'),
  overlay:       $('#canvas-overlay'),
  srvLight:      $('#srv-light'),
  srvText:       $('#srv-text'),
  metaFp:        $('#meta-fp'),
  metaTr:        $('#meta-tr'),
  metaVia:       $('#meta-via'),
  metaNet:       $('#meta-net'),
  metaSrc:       $('#meta-src'),
  netList:       $('#net-list'),
  rulesList:     $('#rules-list'),
  cursor:        $('#cursor-mm'),
  zoom:          $('#zoom-level'),
  status:        $('#status-msg'),
  // toolbar
  btnFit:        $('#btn-fit'),
  btnZoomIn:     $('#btn-zoom-in'),
  btnZoomOut:    $('#btn-zoom-out'),
  btnLoadSample: $('#btn-load-sample'),
  btnClear:      $('#btn-clear'),
  btnRoute:      $('#btn-route'),
  btnDrc:        $('#btn-drc'),
  btnSendKicad:  $('#btn-send-kicad'),
  btnAccept:     $('#btn-accept'),
  btnReject:     $('#btn-reject'),
  // route panel
  routeIdle:     $('#route-idle'),
  routeRunning: $('#route-running'),
  routeDone:    $('#route-done'),
  routeError:   $('#route-error'),
  routeBar:     $('#route-bar'),
  routePct:     $('#route-pct'),
  routeEngine:  $('#route-engine'),
  routeLog:     $('#route-log'),
  // drc panel
  drcSummary:   $('#drc-summary'),
  drcList:      $('#drc-list'),
};

const renderer = new BoardRenderer(els.canvas);
let lastBoardSig = null;
let activeJobId  = null;
let pollingJob   = false;

/* ---- Server health ---------------------------------------------------- */

async function pollHealth() {
  try {
    const r = await fetch('/api/health');
    if (!r.ok) throw new Error('not ok');
    const d = await r.json();
    els.srvLight.classList.add('ok');
    els.srvLight.classList.remove('fail');
    els.srvText.textContent = `${d.product} v${d.version}`;
  } catch (e) {
    els.srvLight.classList.add('fail');
    els.srvLight.classList.remove('ok');
    els.srvText.textContent = 'server unreachable';
  }
}

/* ---- Board state polling --------------------------------------------- */

async function pollBoard() {
  try {
    const info = await (await fetch('/api/info')).json();
    if (!info.loaded) {
      if (lastBoardSig !== null) {
        renderer.clear();
        showEmptyState(true);
        updateSidebar(null);
        clearDrcDisplay();
        lastBoardSig = null;
      }
      return;
    }
    const sig = info.received_at;
    if (sig === lastBoardSig) return;
    const board = await (await fetch('/api/board')).json();
    renderer.setBoard(board);
    showEmptyState(false);
    updateSidebar(board, info);
    // A new board invalidates DRC results
    clearDrcDisplay();
    lastBoardSig = sig;
    setStatus(`board loaded (${info.counts.footprints} footprints, ` +
              `${info.counts.tracks} tracks, ${info.counts.nets} nets)`);
  } catch (e) {
    /* ignore — health poller surfaces server issues */
  }
}

function showEmptyState(show) { els.overlay.classList.toggle('hidden', !show); }

function updateSidebar(board, info) {
  if (!board) {
    els.metaFp.textContent = '—';
    els.metaTr.textContent = '—';
    els.metaVia.textContent = '—';
    els.metaNet.textContent = '—';
    els.metaSrc.textContent = '—';
    els.netList.innerHTML = '<li class="muted">No nets to show.</li>';
    els.rulesList.innerHTML = '<dt>—</dt><dd>load a board</dd>';
    return;
  }
  const c = info.counts;
  els.metaFp.textContent  = c.footprints;
  els.metaTr.textContent  = c.tracks;
  els.metaVia.textContent = c.vias;
  els.metaNet.textContent = c.nets;
  els.metaSrc.textContent = info.source || '—';

  const nets = collectNetStats(board);
  els.netList.innerHTML = '';
  for (const ns of nets) {
    const li = document.createElement('li');
    const swatch = document.createElement('span');
    swatch.className = 'net-swatch';
    swatch.style.background = renderer.netColors.get(ns.name) || '#666';
    const name = document.createElement('span');
    name.textContent = ns.name;
    const stats = document.createElement('span');
    stats.className = 'net-stats';
    stats.textContent = `${ns.tracks}t / ${ns.vias}v`;
    li.append(swatch, name, stats);
    li.addEventListener('click', () => toggleNetSelection(li, ns.name));
    els.netList.appendChild(li);
  }

  const rules = (board.design_rules && board.design_rules.design_settings) || {};
  els.rulesList.innerHTML = '';
  for (const [k, v] of Object.entries(rules)) {
    const dt = document.createElement('dt'); dt.textContent = k.replace(/_/g, ' ');
    const dd = document.createElement('dd'); dd.textContent = v;
    els.rulesList.append(dt, dd);
  }
  if (!Object.keys(rules).length) {
    els.rulesList.innerHTML = '<dt>none</dt><dd>—</dd>';
  }
}

function collectNetStats(board) {
  const m = new Map();
  const get = (n) => {
    if (!m.has(n)) m.set(n, { name: n, tracks: 0, vias: 0, pads: 0 });
    return m.get(n);
  };
  (board.tracks || []).forEach(t => t.net && get(t.net).tracks++);
  (board.vias || []).forEach(v => v.net && get(v.net).vias++);
  (board.footprints || []).forEach(fp =>
    (fp.pads || []).forEach(p => p.net && get(p.net).pads++));
  return [...m.values()].sort((a, b) => {
    if (b.tracks !== a.tracks) return b.tracks - a.tracks;
    return a.name.localeCompare(b.name);
  });
}

function toggleNetSelection(li, name) {
  li.classList.toggle('selected');
  const sel = [...els.netList.querySelectorAll('li.selected')]
    .map(x => x.querySelector('span:not(.net-swatch):not(.net-stats)').textContent);
  renderer.setSelectedNets(sel);
}

/* ---- Routing lifecycle ------------------------------------------------ */

async function startRoute() {
  showRoutePane('running');
  els.routeBar.style.width = '0%';
  els.routePct.textContent = '0%';
  els.routeLog.textContent = '';
  els.btnRoute.disabled = true;

  try {
    const r = await fetch('/api/route', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ engine: 'freerouting', max_passes: 30 }),
    });
    const d = await r.json();
    if (!r.ok) {
      const detailMsg = d.details
        ? (d.details.errors || []).join('\n')
        : (d.error || 'route failed');
      showRouteError(detailMsg);
      return;
    }
    activeJobId = d.job_id;
    setStatus(`routing job ${activeJobId} started`);
    pollJob();
  } catch (e) {
    showRouteError(`request failed: ${e}`);
  }
}

async function pollJob() {
  if (!activeJobId || pollingJob) return;
  pollingJob = true;
  try {
    while (activeJobId) {
      const r = await fetch(`/api/route/status/${activeJobId}`);
      if (!r.ok) {
        showRouteError('lost track of job');
        break;
      }
      const d = (await r.json()).status || {};
      els.routeBar.style.width = `${d.progress || 0}%`;
      els.routePct.textContent = `${(d.progress || 0).toFixed(0)}%`;
      els.routeEngine.textContent = d.engine || '?';
      if (Array.isArray(d.log_tail)) {
        els.routeLog.textContent = d.log_tail.slice(-20).join('\n');
        els.routeLog.scrollTop = els.routeLog.scrollHeight;
      }
      if (d.status === 'done') {
        await onRouteDone(d);
        break;
      }
      if (d.status === 'failed') {
        showRouteError(d.error || 'unknown failure');
        break;
      }
      await new Promise(r => setTimeout(r, 700));
    }
  } finally {
    pollingJob = false;
  }
}

async function onRouteDone(jobStatus) {
  const r = await fetch('/api/result');
  if (!r.ok) {
    showRouteError('result not retrievable');
    return;
  }
  const d = await r.json();

  // Preview the routed board on the canvas WITHOUT replacing server state yet.
  renderer.setBoard(d.board);
  setStatus(
    `routed: +${d.added_tracks.length} tracks, ` +
    `+${d.added_vias.length} vias in ${d.elapsed.toFixed(1)}s`
  );
  showRoutePane('done', {
    added_tracks: d.added_tracks.length,
    added_vias:   d.added_vias.length,
    elapsed:      d.elapsed,
    engine:       d.engine,
  });
}

async function acceptResult() {
  const r = await fetch('/api/result/accept', { method: 'POST' });
  if (r.ok) {
    setStatus('routes accepted; board state updated');
    showRoutePane('idle');
    activeJobId = null;
    els.btnRoute.disabled = false;
    // pollBoard will pick up the new state on its next tick
  } else {
    setStatus('accept failed');
  }
}

function rejectResult() {
  // Re-fetch the un-routed board from the server to discard the preview
  fetch('/api/board')
    .then(r => r.ok ? r.json() : null)
    .then(b => { if (b) renderer.setBoard(b); });
  showRoutePane('idle');
  activeJobId = null;
  els.btnRoute.disabled = false;
  setStatus('routes discarded');
}

function showRoutePane(which, summary) {
  for (const id of ['routeIdle', 'routeRunning', 'routeDone', 'routeError']) {
    els[id].classList.add('hidden');
  }
  if (which === 'idle')    els.routeIdle.classList.remove('hidden');
  if (which === 'running') els.routeRunning.classList.remove('hidden');
  if (which === 'done') {
    els.routeDone.classList.remove('hidden');
    if (summary) {
      els.routeDone.querySelector('.route-summary').innerHTML =
        `Engine <strong>${summary.engine}</strong> — added ` +
        `<strong>${summary.added_tracks}</strong> tracks and ` +
        `<strong>${summary.added_vias}</strong> vias in ` +
        `<strong>${summary.elapsed.toFixed(1)}s</strong>.`;
    }
  }
  if (which === 'error') els.routeError.classList.remove('hidden');
}

function showRouteError(msg) {
  showRoutePane('error');
  els.routeError.textContent = msg;
  els.btnRoute.disabled = false;
  activeJobId = null;
  setStatus('route failed');
}

/* ---- DRC -------------------------------------------------------------- */

async function runDrc() {
  setStatus('running DRC...');
  const r = await fetch('/api/drc', { method: 'POST' });
  if (!r.ok) {
    setStatus('DRC failed');
    return;
  }
  const d = await r.json();
  els.drcSummary.classList.remove('muted');
  if (d.total === 0) {
    els.drcSummary.textContent = '✓ No violations';
    els.drcSummary.style.color = '#4ade80';
  } else {
    els.drcSummary.textContent =
      `${d.total} violation${d.total === 1 ? '' : 's'}: ` +
      `${d.counts.error} error, ${d.counts.warning} warning`;
    els.drcSummary.style.color = '#ef4444';
  }
  // List
  els.drcList.innerHTML = '';
  for (const v of d.violations) {
    const li = document.createElement('li');
    li.className = `drc-item drc-${v.level}`;
    li.innerHTML =
      `<span class="drc-code">${v.code}</span>` +
      `<span class="drc-msg">${v.msg}</span>` +
      `<span class="drc-loc">${v.x_mm.toFixed(2)}, ${v.y_mm.toFixed(2)}</span>`;
    els.drcList.appendChild(li);
  }
  renderer.setViolations(d.violations);
  setStatus(`DRC: ${d.total} violation${d.total === 1 ? '' : 's'}`);
}

function clearDrcDisplay() {
  els.drcSummary.classList.add('muted');
  els.drcSummary.style.color = '';
  els.drcSummary.textContent = 'Not yet run.';
  els.drcList.innerHTML = '';
  if (renderer.setViolations) renderer.setViolations([]);
}

/* ---- Buttons ---------------------------------------------------------- */

els.btnFit.addEventListener('click',     () => renderer.fit());
els.btnZoomIn.addEventListener('click',  () => renderer.zoom(1.2,
  els.canvas.clientWidth / 2, els.canvas.clientHeight / 2));
els.btnZoomOut.addEventListener('click', () => renderer.zoom(1 / 1.2,
  els.canvas.clientWidth / 2, els.canvas.clientHeight / 2));
els.btnClear.addEventListener('click', async () => {
  await fetch('/api/board', { method: 'DELETE' });
  showRoutePane('idle');
  setStatus('board cleared');
});

els.btnLoadSample.addEventListener('click', async () => {
  setStatus('loading sample board...');
  try {
    const sample = await (await fetch('/static/sample_board.json')).json();
    const r = await fetch('/api/board?source=sample', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(sample),
    });
    if (!r.ok) throw new Error(await r.text());
    setStatus('sample loaded');
  } catch (e) {
    setStatus(`failed to load sample: ${e}`);
  }
});

els.btnRoute.addEventListener('click',  startRoute);
els.btnDrc.addEventListener('click',    runDrc);
els.btnAccept.addEventListener('click', acceptResult);
els.btnReject.addEventListener('click', rejectResult);

els.btnSendKicad.addEventListener('click', showSendToKicadHelp);

function showSendToKicadHelp() {
  // Find out what's in the current board so we can tell the user what they're sending
  fetch('/api/info').then(r => r.json()).then(info => {
    const c = (info && info.counts) || {};
    const tracks = c.tracks || 0;
    const vias   = c.vias   || 0;
    const source = info && info.source || '?';

    const isRouted = source.startsWith('routed-');

    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.innerHTML = `
      <div class="modal-card">
        <h2>Send to KiCad</h2>
        ${isRouted
          ? `<p class="modal-good">Board is ready: <strong>${tracks}</strong> tracks
             and <strong>${vias}</strong> vias from <strong>${source}</strong>.</p>`
          : `<p class="modal-warn">The current board is unrouted (no routes accepted).
             You probably want to Auto-route first, then Accept the result.</p>`}
        <p>KiRouter cannot push routes directly to KiCad
        (browser security). The KiBridge plugin pulls them on demand.</p>
        <ol class="modal-steps">
          <li>Switch to <strong>KiCad PCB Editor</strong></li>
          <li>Click <strong>KiBridge: Import from KiRouter</strong> in the toolbar
              <em>(or PCB menu &rarr; PSS Tools)</em></li>
          <li>Confirm the dialog &rarr; KiCad backs up your .kicad_pcb and
              applies the new tracks and vias</li>
          <li>Press <strong>Ctrl+S</strong> in KiCad to save</li>
        </ol>
        <p class="modal-small">Don't see the button? Run
        <code>INSTALL.bat</code> in the kibridge folder and restart KiCad.</p>
        <div class="modal-actions">
          <button class="btn btn-primary" id="modal-close">Got it</button>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);

    const close = () => overlay.remove();
    overlay.querySelector('#modal-close').addEventListener('click', close);
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) close();
    });
  });
}

document.querySelectorAll('.layer-toggles input').forEach(cb => {
  cb.addEventListener('change', (e) =>
    renderer.setLayerVisible(e.target.dataset.layer, e.target.checked));
});

/* ---- Statusbar updates from renderer ---------------------------------- */

window.addEventListener('kirouter:cursor', (e) => {
  const c = e.detail;
  els.cursor.textContent = c
    ? `x: ${c.x.toFixed(2)}mm, y: ${c.y.toFixed(2)}mm`
    : 'x: —, y: —';
});
window.addEventListener('kirouter:zoom', (e) => {
  const pct = Math.round(e.detail / 6 * 100);
  els.zoom.textContent = `zoom: ${pct}%`;
});

function setStatus(msg) { els.status.textContent = msg; }

/* ---- Boot ------------------------------------------------------------- */

pollHealth();
pollBoard();
showRoutePane('idle');
setInterval(pollHealth, 5000);
setInterval(pollBoard, 1500);
