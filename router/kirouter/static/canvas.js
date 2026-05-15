/* ====================================================================
   KiRouter board renderer.

   Coordinates: KiCad/board uses millimetres, with +X right and +Y down,
   origin at (0, 0) (top-left of work area). We mirror that.
   View transform is (offsetX_px, offsetY_px) + scale (px per mm).
   ==================================================================== */

class BoardRenderer {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx    = canvas.getContext('2d');
    this.dpr    = window.devicePixelRatio || 1;

    this.board  = null;
    this.scale  = 6;      // pixels per mm
    this.offset = { x: 40, y: 40 };
    this.layerVisibility = {
      'F.Cu':    true,
      'B.Cu':    true,
      'F.SilkS': true,
      'B.SilkS': false,
      'F.Fab':   false,
      'B.Fab':   false,
      'User.1':  true,
    };
    this.netColors    = new Map();
    this.selectedNets = new Set();   // for highlighting; populated by app.js
    this.violations   = [];          // DRC violation markers
    this.cursorMm     = null;

    this._installInteraction();
    this._resize();
    window.addEventListener('resize', () => this._resize());
  }

  /* ---- public API ---------------------------------------------------- */

  setBoard(board) {
    this.board = board;
    this.violations = [];
    this._assignNetColors();
    this.fit();
  }

  clear() {
    this.board = null;
    this.netColors.clear();
    this.selectedNets.clear();
    this.violations = [];
    this._draw();
  }

  setLayerVisible(layer, visible) {
    this.layerVisibility[layer] = visible;
    this._draw();
  }

  setSelectedNets(nets) {
    this.selectedNets = new Set(nets);
    this._draw();
  }

  setViolations(violations) {
    this.violations = Array.isArray(violations) ? violations : [];
    this._draw();
  }

  fit() {
    if (!this.board) { this._draw(); return; }
    const bbox = this._boardBbox();
    if (!bbox) { this._draw(); return; }
    const w_mm = Math.max(bbox.x_max - bbox.x_min, 1);
    const h_mm = Math.max(bbox.y_max - bbox.y_min, 1);
    const cw = this.canvas.clientWidth, ch = this.canvas.clientHeight;
    const margin = 40;
    const scaleX = (cw - margin) / w_mm;
    const scaleY = (ch - margin) / h_mm;
    this.scale = Math.min(scaleX, scaleY);
    this.offset.x = (cw - w_mm * this.scale) / 2 - bbox.x_min * this.scale;
    this.offset.y = (ch - h_mm * this.scale) / 2 - bbox.y_min * this.scale;
    this._draw();
  }

  zoom(delta, cx, cy) {
    // Zoom around (cx, cy) screen pixel.
    const newScale = Math.max(0.5, Math.min(80, this.scale * delta));
    const factor = newScale / this.scale;
    this.offset.x = cx - (cx - this.offset.x) * factor;
    this.offset.y = cy - (cy - this.offset.y) * factor;
    this.scale = newScale;
    this._draw();
  }

  /* ---- internals ----------------------------------------------------- */

  _resize() {
    const r = this.canvas.getBoundingClientRect();
    this.canvas.width  = Math.floor(r.width  * this.dpr);
    this.canvas.height = Math.floor(r.height * this.dpr);
    this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    this._draw();
  }

  _installInteraction() {
    let dragging = false;
    let lastX = 0, lastY = 0;

    this.canvas.addEventListener('mousedown', (e) => {
      dragging = true;
      lastX = e.clientX; lastY = e.clientY;
    });
    window.addEventListener('mouseup', () => { dragging = false; });
    window.addEventListener('mousemove', (e) => {
      const r = this.canvas.getBoundingClientRect();
      const lx = e.clientX - r.left, ly = e.clientY - r.top;
      // Track cursor position in mm
      const x_mm = (lx - this.offset.x) / this.scale;
      const y_mm = (ly - this.offset.y) / this.scale;
      this.cursorMm = { x: x_mm, y: y_mm };
      this._emitCursor();

      if (dragging) {
        const dx = e.clientX - lastX, dy = e.clientY - lastY;
        this.offset.x += dx; this.offset.y += dy;
        lastX = e.clientX; lastY = e.clientY;
        this._draw();
      }
    });

    this.canvas.addEventListener('wheel', (e) => {
      e.preventDefault();
      const r = this.canvas.getBoundingClientRect();
      const cx = e.clientX - r.left, cy = e.clientY - r.top;
      const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15;
      this.zoom(factor, cx, cy);
    }, { passive: false });
  }

  _emitCursor() {
    const ev = new CustomEvent('kirouter:cursor', { detail: this.cursorMm });
    window.dispatchEvent(ev);
    const zev = new CustomEvent('kirouter:zoom', { detail: this.scale });
    window.dispatchEvent(zev);
  }

  _boardBbox() {
    if (!this.board) return null;
    const meta = this.board.meta || {};
    if (meta.board_bbox) return meta.board_bbox;
    // Fallback: compute from footprints + tracks
    let x_min = +Infinity, y_min = +Infinity;
    let x_max = -Infinity, y_max = -Infinity;
    const expand = (x, y) => {
      if (x < x_min) x_min = x; if (x > x_max) x_max = x;
      if (y < y_min) y_min = y; if (y > y_max) y_max = y;
    };
    (this.board.footprints || []).forEach(fp => expand(fp.x_mm || 0, fp.y_mm || 0));
    (this.board.tracks || []).forEach(t => {
      expand(t.start.x_mm, t.start.y_mm);
      expand(t.end.x_mm,   t.end.y_mm);
    });
    if (!isFinite(x_min)) return null;
    const pad = 5;
    return {
      x_min: x_min - pad, y_min: y_min - pad,
      x_max: x_max + pad, y_max: y_max + pad,
    };
  }

  _assignNetColors() {
    const PALETTE = [
      '#ff6b6b','#feca57','#48dbfb','#ff9ff3','#54a0ff',
      '#5f27cd','#00d2d3','#ff6348','#1dd1a1','#c8d6e5',
      '#ee5253','#10ac84','#576574','#222f3e','#01a3a4',
    ];
    const nets = new Set();
    (this.board.tracks || []).forEach(t => t.net && nets.add(t.net));
    (this.board.vias   || []).forEach(v => v.net && nets.add(v.net));
    (this.board.footprints || []).forEach(fp =>
      (fp.pads || []).forEach(p => p.net && nets.add(p.net)));
    let i = 0;
    this.netColors.clear();
    [...nets].sort().forEach(n => {
      // Special-case GND family
      if (/^(GND|AGND|DGND|EARTH)$/i.test(n)) {
        this.netColors.set(n, '#888');
      } else {
        this.netColors.set(n, PALETTE[i % PALETTE.length]);
        i++;
      }
    });
  }

  _draw() {
    const ctx = this.ctx;
    const w = this.canvas.clientWidth, h = this.canvas.clientHeight;
    ctx.clearRect(0, 0, w, h);

    // Backdrop grid
    this._drawGrid();

    if (!this.board) return;

    // Board outline
    this._drawBoardOutline();

    // Tracks (back layer first so front overlays)
    if (this.layerVisibility['B.Cu']) this._drawTracks('B.Cu');
    if (this.layerVisibility['F.Cu']) this._drawTracks('F.Cu');

    // Vias (always visible if any cu layer is on)
    if (this.layerVisibility['F.Cu'] || this.layerVisibility['B.Cu']) {
      this._drawVias();
    }

    // Footprints + pads
    this._drawFootprints();

    // Selection highlight (if any nets selected)
    if (this.selectedNets.size > 0) this._drawSelectionOverlay();

    // DRC violation markers (always on top)
    if (this.violations.length > 0) this._drawViolations();
  }

  _drawViolations() {
    const ctx = this.ctx;
    ctx.save();
    for (const v of this.violations) {
      const [cx, cy] = this._toScreen(v.x_mm, v.y_mm);
      const isError = v.level === 'error';
      const color = isError ? '#ef4444' : '#fbbf24';
      // Outer glow ring
      ctx.beginPath();
      ctx.arc(cx, cy, 12, 0, Math.PI * 2);
      ctx.fillStyle = color + '33';
      ctx.fill();
      // Crosshair
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(cx - 10, cy); ctx.lineTo(cx + 10, cy);
      ctx.moveTo(cx, cy - 10); ctx.lineTo(cx, cy + 10);
      ctx.stroke();
      // Center dot
      ctx.beginPath();
      ctx.arc(cx, cy, 3, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.fill();
    }
    ctx.restore();
  }

  _drawGrid() {
    const ctx = this.ctx;
    const w = this.canvas.clientWidth, h = this.canvas.clientHeight;
    ctx.fillStyle = '#0d0d0d';
    ctx.fillRect(0, 0, w, h);

    if (this.scale < 3) return;
    ctx.strokeStyle = '#1f1f1f';
    ctx.lineWidth = 1;
    const step_mm = this.scale > 25 ? 1 : (this.scale > 8 ? 5 : 10);
    const step_px = step_mm * this.scale;
    const startX = ((this.offset.x % step_px) + step_px) % step_px;
    const startY = ((this.offset.y % step_px) + step_px) % step_px;
    ctx.beginPath();
    for (let x = startX; x < w; x += step_px) {
      ctx.moveTo(x, 0); ctx.lineTo(x, h);
    }
    for (let y = startY; y < h; y += step_px) {
      ctx.moveTo(0, y); ctx.lineTo(w, y);
    }
    ctx.stroke();
  }

  _toScreen(x_mm, y_mm) {
    return [
      this.offset.x + x_mm * this.scale,
      this.offset.y + y_mm * this.scale,
    ];
  }

  _drawBoardOutline() {
    const bbox = this._boardBbox();
    if (!bbox) return;
    const ctx = this.ctx;
    const [x1, y1] = this._toScreen(bbox.x_min, bbox.y_min);
    const [x2, y2] = this._toScreen(bbox.x_max, bbox.y_max);
    ctx.strokeStyle = '#665b3a';
    ctx.lineWidth = 1.5;
    ctx.setLineDash([6, 4]);
    ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
    ctx.setLineDash([]);
  }

  _drawTracks(layer) {
    const ctx = this.ctx;
    (this.board.tracks || []).forEach(t => {
      if (t.layer !== layer) return;
      const color = this.netColors.get(t.net) || '#888';
      const [sx, sy] = this._toScreen(t.start.x_mm, t.start.y_mm);
      const [ex, ey] = this._toScreen(t.end.x_mm,   t.end.y_mm);
      const w_px = Math.max(1, t.width_mm * this.scale);
      ctx.strokeStyle = layer === 'F.Cu' ? color : this._dim(color);
      ctx.lineWidth = w_px;
      ctx.lineCap = 'round';
      ctx.beginPath();
      ctx.moveTo(sx, sy); ctx.lineTo(ex, ey);
      ctx.stroke();
    });
  }

  _drawVias() {
    const ctx = this.ctx;
    (this.board.vias || []).forEach(v => {
      const [cx, cy] = this._toScreen(v.x_mm, v.y_mm);
      const r = Math.max(2, (v.width_mm / 2) * this.scale);
      ctx.fillStyle = '#c4a484';
      ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.fill();
      // Drill hole
      const dr = Math.max(1, ((v.drill_mm || v.width_mm * 0.5) / 2) * this.scale);
      ctx.fillStyle = '#000';
      ctx.beginPath(); ctx.arc(cx, cy, dr, 0, Math.PI * 2); ctx.fill();
    });
  }

  _drawFootprints() {
    const ctx = this.ctx;
    (this.board.footprints || []).forEach(fp => {
      const [cx, cy] = this._toScreen(fp.x_mm || 0, fp.y_mm || 0);

      // Footprint label
      if (this.layerVisibility['F.SilkS'] || this.layerVisibility['B.SilkS']) {
        ctx.fillStyle = '#aaa';
        ctx.font = '10px monospace';
        ctx.textAlign = 'center';
        ctx.fillText(fp.ref || '?', cx, cy - 8);
      }

      // Pads
      const pads = fp.pads || [];
      if (pads.length === 0) {
        // Fallback dot when pads aren't exported yet
        ctx.fillStyle = '#4ec9b0';
        ctx.beginPath(); ctx.arc(cx, cy, 3, 0, Math.PI * 2); ctx.fill();
      } else {
        pads.forEach(pad => {
          const [px, py] = this._toScreen(pad.x_mm, pad.y_mm);
          const sx = (pad.size_mm?.[0] || 1) * this.scale;
          const sy = (pad.size_mm?.[1] || 1) * this.scale;
          ctx.fillStyle = this.netColors.get(pad.net) || '#4ec9b0';
          if (pad.shape === 'circle') {
            ctx.beginPath(); ctx.arc(px, py, sx / 2, 0, Math.PI * 2); ctx.fill();
          } else {
            ctx.fillRect(px - sx / 2, py - sy / 2, sx, sy);
          }
        });
      }
    });
  }

  _drawSelectionOverlay() {
    const ctx = this.ctx;
    ctx.save();
    ctx.globalAlpha = 0.85;
    (this.board.tracks || []).forEach(t => {
      if (!this.selectedNets.has(t.net)) return;
      const [sx, sy] = this._toScreen(t.start.x_mm, t.start.y_mm);
      const [ex, ey] = this._toScreen(t.end.x_mm,   t.end.y_mm);
      const w_px = Math.max(2, t.width_mm * this.scale + 3);
      ctx.strokeStyle = '#ffeb3b';
      ctx.lineWidth = w_px;
      ctx.lineCap = 'round';
      ctx.beginPath(); ctx.moveTo(sx, sy); ctx.lineTo(ex, ey); ctx.stroke();
    });
    ctx.restore();
  }

  _dim(hex) {
    // Return a darker version for back-layer tracks.
    if (!hex || hex[0] !== '#' || hex.length !== 7) return '#555';
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    const f = (c) => Math.max(0, Math.min(255, Math.round(c * 0.55)));
    const h = (c) => f(c).toString(16).padStart(2, '0');
    return `#${h(r)}${h(g)}${h(b)}`;
  }
}

window.BoardRenderer = BoardRenderer;
