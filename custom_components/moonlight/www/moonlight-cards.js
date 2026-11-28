// MoonLight Lovelace cards. Basic is power, brightness, palette and looks.
// Pro is the Control desk: display strip, switches, encoder dials, faders and preset pads.
// Effects is the Effects page: one tab per layer, and each effect on that layer as its own card.
//
// Both cards are given the Control light and find every other control on that device
// by state attributes. Home Assistant's entity registry does not send unique_id.
// `module` and `control` mark a desk slot. `moonlight: "look"` is the effect list.
// `moonlight: "pad"` and `slot` are a preset pad. The table is under "Lovelace cards"
// in docs/integration.md.
//
// Channel 1 is the light: switch1 power, fader1 brightness, encoder1 the palette index.
// Channels 2-8 are the desk entities. A missing slot stays in the column, dimmed.
//
// The dial and the sixteen-segment map follow buildKnob and SEG16 in MoonLight's
// src/ui/app.js. A hass update rebuilds this tree. _gesture holds that off while a
// pointer is down, so the rebuild does not take the control out from under the finger.

const BASIC = "moonlight-basic-card";
const PRO = "moonlight-pro-card";
const EFFECTS = "moonlight-effects-card";

const CHANNELS = 8;
const STRIP_CELLS = 28;
// Vertical pixels that cover the whole dial range. The device UI uses the same travel.
const DRAG_TRAVEL = 150;
const KNOB_SWEEP = 0.75;

const SEG16 = Object.fromEntries(
  Object.entries({
    "0": "a1 a2 b c d1 d2 e f",
    "1": "b c",
    "2": "a1 a2 b g1 g2 e d1 d2",
    "3": "a1 a2 b c d1 d2 g1 g2",
    "4": "f b g1 g2 c",
    "5": "a1 a2 f g1 g2 c d1 d2",
    "6": "a1 a2 f g1 g2 e c d1 d2",
    "7": "a1 a2 b c",
    "8": "a1 a2 b c d1 d2 e f g1 g2",
    "9": "a1 a2 b c d1 d2 f g1 g2",
    A: "a1 a2 b c e f g1 g2",
    B: "a1 a2 b c d1 d2 g2 j m",
    C: "a1 a2 f e d1 d2",
    D: "a1 a2 b c d1 d2 j m",
    E: "a1 a2 f e d1 d2 g1 g2",
    F: "a1 a2 f e g1 g2",
    G: "a1 a2 f e d1 d2 c g2",
    H: "b c e f g1 g2",
    I: "a1 a2 d1 d2 j m",
    J: "b c d1 d2 e",
    K: "e f g1 k l",
    L: "f e d1 d2",
    M: "b c e f h k",
    N: "b c e f h l",
    O: "a1 a2 b c d1 d2 e f",
    P: "a1 a2 b e f g1 g2",
    Q: "a1 a2 b c d1 d2 e f l",
    R: "a1 a2 b e f g1 g2 l",
    S: "a1 a2 f g1 g2 c d1 d2",
    T: "a1 a2 j m",
    U: "b c d1 d2 e f",
    V: "e f k n",
    W: "b c e f n l",
    X: "h k n l",
    Y: "h k m",
    Z: "a1 a2 k n d1 d2",
    "-": "g1 g2",
    "+": "g1 g2 j m",
    ".": "d1",
    ":": "j m",
    "/": "k n",
    " ": "",
  }).map(([ch, segs]) => [ch, new Set(segs.split(" ").filter(Boolean))]),
);
const EMPTY_SEGS = new Set();

function deviceOf(hass, entityId) {
  const entities = hass.entities || {};
  const deviceId = entities[entityId] && entities[entityId].device_id;
  if (!deviceId) return { deviceId: null, entries: [] };
  const entries = Object.keys(entities)
    .filter((id) => entities[id].device_id === deviceId)
    .map((id) => ({ id, state: hass.states[id] }));
  return { deviceId, entries };
}

function field(entry, key) {
  return entry && entry.state && entry.state.attributes ? entry.state.attributes[key] : undefined;
}

// The driven control, after the device name and the bank prefix. `1 Switch 2 · Ampm` is `Ampm`.
// An empty slot is `Switch 2`.
function labelOf(state) {
  if (!state) return "";
  let name = state.attributes.friendly_name || state.entity_id;
  const deviceMark = name.lastIndexOf("Control ");
  if (deviceMark >= 0) name = name.slice(deviceMark + "Control ".length);
  const driven = name.lastIndexOf(" · ");
  if (driven >= 0) return name.slice(driven + 3);
  return name.replace(/^[1-4] /, "");
}

function writeControl(hass, deviceId, control, value) {
  // device_id stays in the data. A target argument is a list, and the action wants one id.
  hass.callService("moonlight", "set_control", {
    device_id: deviceId,
    module: "Control",
    control,
    value: JSON.stringify(value),
  });
}

function lightLevel(state) {
  // Home Assistant sets brightness to null while the light is off. The desk fader is `level`.
  const attributes = (state && state.attributes) || {};
  if (typeof attributes.brightness === "number" && Number.isFinite(attributes.brightness)) return attributes.brightness;
  if (typeof attributes.level === "number" && Number.isFinite(attributes.level)) return attributes.level;
  return 0;
}

function slot(entries, name) {
  return entries.find((entry) => field(entry, "module") === "Control" && field(entry, "control") === name);
}

function lookEntry(entries) {
  return entries.find((entry) => field(entry, "moonlight") === "look");
}

// One sixteen-segment cell. The coordinates are seg16Cell in MoonLight's src/ui/app.js:
// 14 units wide, 20 tall, 1.5-unit strokes.
function segParts(ox) {
  const stroke = 1.5;
  const bar = (x, y, w, h) => `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="0.75"/>`;
  const diag = (x1, y1, x2, y2) =>
    `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke-width="1.5" stroke-linecap="round"/>`;
  return {
    a1: bar(ox + 2, 1, 3, stroke),
    a2: bar(ox + 6, 1, 3, stroke),
    d1: bar(ox + 2, 17.5, 3, stroke),
    d2: bar(ox + 6, 17.5, 3, stroke),
    g1: bar(ox + 2, 9.25, 3, stroke),
    g2: bar(ox + 6, 9.25, 3, stroke),
    f: bar(ox + 0.25, 2, stroke, 7),
    b: bar(ox + 9.25, 2, stroke, 7),
    e: bar(ox + 0.25, 11, stroke, 7),
    c: bar(ox + 9.25, 11, stroke, 7),
    j: bar(ox + 4.75, 2, stroke, 7),
    m: bar(ox + 4.75, 11, stroke, 7),
    h: diag(ox + 2.7, 3.5, ox + 4.3, 7.9),
    k: diag(ox + 8.3, 3.5, ox + 6.7, 7.9),
    n: diag(ox + 2.7, 16.9, ox + 4.3, 12.4),
    l: diag(ox + 8.3, 16.9, ox + 6.7, 12.4),
  };
}

function segSvg(text, chars, stretch) {
  const shown = String(text ?? "").toUpperCase();
  let body = "";
  for (let index = 0; index < chars; index += 1) {
    const on = SEG16[shown[index]] || EMPTY_SEGS;
    const parts = segParts(index * 14 + 1);
    for (const name of Object.keys(parts)) {
      const cls = on.has(name) ? "seg16-on" : "seg16-off";
      body += parts[name].replace(/^<(rect|line) /, `<$1 class="${cls}" `);
    }
  }
  const ratio = stretch ? ' preserveAspectRatio="none"' : "";
  const kind = stretch ? "seg-strip" : "seg-readout";
  return `<div class="seg16 ${kind}"><svg viewBox="0 0 ${chars * 14} 20"${ratio} aria-hidden="true">${body}</svg></div>`;
}

function readout(value) {
  return segSvg(String(Math.round(Number(value) || 0)).padStart(3, " ").slice(-3), 3, false);
}

// 270° sweep from 7 o'clock to 5 o'clock. The track is a full ring, the same endless encoder the desk draws.
function knobSvg(fraction) {
  const circ = 2 * Math.PI * 15;
  const sweep = KNOB_SWEEP;
  const frac = Math.min(1, Math.max(0, fraction || 0));
  const ang = ((135 + frac * 270) * Math.PI) / 180;
  const at = (radius) => [20 + radius * Math.cos(ang), 20 + radius * Math.sin(ang)];
  const [x1, y1] = at(6);
  const [x2, y2] = at(13);
  const n = (value) => value.toFixed(2);
  return `<svg viewBox="0 0 40 40" aria-hidden="true">
    <circle class="knob-face" cx="20" cy="20" r="12"/>
    <circle class="knob-track" cx="20" cy="20" r="15" transform="rotate(135 20 20)" stroke-dasharray="${n(circ)} ${n(circ)}"/>
    <circle class="knob-fill" cx="20" cy="20" r="15" transform="rotate(135 20 20)" stroke-dasharray="${n(circ * sweep * frac)} ${n(circ)}"/>
    <line class="knob-pointer" x1="${n(x1)}" y1="${n(y1)}" x2="${n(x2)}" y2="${n(y2)}"/>
  </svg>`;
}

function fractionOf(input) {
  const min = Number(input.min);
  const max = Number(input.max);
  const value = Number(input.value);
  if (!Number.isFinite(min) || !Number.isFinite(max) || max <= min) return 0;
  return (value - min) / (max - min);
}

function paintKnob(wrap, input) {
  wrap.innerHTML = knobSvg(fractionOf(input));
  const cell = wrap.parentElement.querySelector(".seg-readout");
  if (cell) cell.outerHTML = readout(input.value);
}

function bindKnob(wrap, input, onCommit, hold) {
  const commit = () => onCommit(Number(input.value));
  wrap.addEventListener("pointerdown", (event) => {
    event.preventDefault();
    wrap.setPointerCapture(event.pointerId);
    wrap.classList.add("turning");
    hold(true);
    const startY = event.clientY;
    const startV = Number(input.value);
    const min = Number(input.min) || 0;
    const max = Number(input.max) || 0;
    const move = (ev) => {
      const delta = ((startY - ev.clientY) / DRAG_TRAVEL) * (max - min);
      const next = Math.round(Math.min(max, Math.max(min, startV + delta)));
      if (next === Number(input.value)) return;
      input.value = String(next);
      paintKnob(wrap, input);
    };
    let ended = false;
    const up = (ev) => {
      if (ended) return;
      ended = true;
      wrap.classList.remove("turning");
      if (ev && ev.pointerId != null && wrap.hasPointerCapture(ev.pointerId)) wrap.releasePointerCapture(ev.pointerId);
      wrap.removeEventListener("pointermove", move);
      wrap.removeEventListener("pointerup", up);
      wrap.removeEventListener("pointercancel", up);
      wrap.removeEventListener("lostpointercapture", up);
      hold(false);
      commit();
    };
    wrap.addEventListener("pointermove", move);
    wrap.addEventListener("pointerup", up);
    wrap.addEventListener("pointercancel", up);
    wrap.addEventListener("lostpointercapture", up);
  });
  wrap.addEventListener(
    "wheel",
    (event) => {
      event.preventDefault();
      const min = Number(input.min) || 0;
      const max = Number(input.max) || 0;
      const step = Math.max(1, Math.round((max - min) / 100));
      const next = Math.round(Math.min(max, Math.max(min, Number(input.value) + (event.deltaY < 0 ? step : -step))));
      if (next === Number(input.value)) return;
      input.value = String(next);
      paintKnob(wrap, input);
      commit();
    },
    { passive: false },
  );
}

const STYLE = `
  :host {
    display: block;
    width: 100%;
    max-width: 100%;
    min-width: 0;
    box-sizing: border-box;
    --bg-0: #1a1a2e;
    --bg-1: #16213e;
    --fg: #e0e0e0;
    --fg-muted: #a0a0b0;
    --accent: #a78bfa;
    --accent-soft: #6b5b9a;
    --card-bg: #16213e;
    --card-bg-2: #283661;
    --border: #2a3a6a;
    --led: #ff3b30;
    --col: 52px;
    --gap: 4px;
    --channels: 8; /* CHANNELS. The desk is eight columns in both places. */
    color: var(--fg);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    font-size: 15px;
    line-height: 1.35;
  }
  .panel {
    box-sizing: border-box;
    max-width: 100%;
    min-width: 0;
    overflow: hidden;
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 14px;
  }
  button, input { font: inherit; color: inherit; }
  .row { display: flex; align-items: center; gap: 14px; }
  .power {
    display: inline-flex; align-items: center; gap: 12px;
    background: transparent; border: 0; padding: 0; cursor: pointer; color: var(--fg);
  }
  .mark {
    width: 36px; height: 36px; border-radius: 18px; box-sizing: border-box;
    border: 1px solid var(--accent-soft); background: var(--bg-0);
  }
  .power.on .mark { background: var(--accent); border-color: var(--accent); }
  .word { font-size: 18px; font-weight: 600; letter-spacing: 0.01em; }
  .grow { flex: 1; min-width: 0; }
  .hd {
    display: flex; justify-content: space-between; align-items: baseline; gap: 12px;
    margin: 18px 0 8px; font-size: 13px; color: var(--fg-muted);
  }
  .hd.tight { margin-top: 0; }
  .now { color: var(--fg); font-size: 15px; font-variant-numeric: tabular-nums; }
  .search, .slider { width: 100%; box-sizing: border-box; }
  .search {
    background: var(--bg-0); border: 1px solid var(--border); border-radius: 6px;
    padding: 8px 10px; font-size: 15px;
  }
  .slider { accent-color: var(--accent); height: 28px; }
  .list { max-height: 240px; overflow-y: auto; overflow-x: hidden; scrollbar-gutter: stable; margin-top: 8px; }
  .item {
    display: block; width: 100%; text-align: left; background: transparent;
    border: 0; border-bottom: 1px solid var(--border); padding: 10px 8px;
    font-size: 15px; cursor: pointer;
  }
  .item.on { background: var(--card-bg-2); box-shadow: inset 2px 0 0 var(--accent); }
  .looks { display: grid; grid-template-columns: repeat(auto-fill, minmax(96px, 1fr)); gap: 6px; }
  .surface {
    overflow-x: auto;
    overflow-y: hidden;
    scrollbar-gutter: stable;
    max-width: 100%;
    min-width: 0;
  }
  /* Eight fixed columns, the same idea as MoonLight's --surface-col. A card narrower than the
     desk scrolls this strip. Shrinking the columns below this clips the three-digit readout. */
  .meter {
    width: calc(var(--channels) * var(--col) + (var(--channels) - 1) * var(--gap));
    user-select: none;
  }
  .bank-name {
    margin: 10px 0 4px; font-size: 11px; letter-spacing: 0.06em; text-transform: uppercase;
    color: var(--fg-muted);
  }
  .seg-strip { width: 100%; height: 32px; margin-bottom: 14px; }
  .seg-readout { width: 100%; max-width: var(--col); height: 22px; }
  .seg16 svg { display: block; width: 100%; height: 100%; }
  .seg16-on { fill: var(--led); stroke: var(--led); }
  .seg16-off { fill: var(--led); stroke: var(--led); opacity: 0.1; }
  .bank { display: flex; gap: var(--gap); margin-bottom: 12px; align-items: flex-start; }
  .ch {
    position: relative; width: var(--col); flex: 0 0 var(--col);
    display: flex; flex-direction: column; align-items: center; gap: 4px;
  }
  .name {
    width: 100%; font-size: 11px; line-height: 1.25; text-align: center; color: var(--fg-muted);
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  }
  .pill {
    width: 100%; max-width: 40px; height: 18px; border-radius: 9px; border: 1px solid var(--accent-soft);
    background: var(--bg-0); cursor: pointer; padding: 0;
  }
  .pill.on { background: var(--accent); border-color: var(--accent); }
  .knob { width: 40px; height: 40px; touch-action: none; cursor: ns-resize; }
  .knob svg, .knob svg * { pointer-events: none; }
  .knob.turning { filter: brightness(1.2); }
  .knob-face { fill: #10162c; }
  .knob-track { fill: none; stroke: color-mix(in srgb, var(--fg) 22%, var(--border)); stroke-width: 4; }
  .knob-fill { fill: none; stroke: var(--accent); stroke-width: 4; stroke-linecap: round; }
  .knob-pointer { stroke: var(--fg); stroke-width: 2.4; stroke-linecap: round; }
  .encoder-input {
    position: absolute; width: 1px; height: 1px; opacity: 0; margin: 0; padding: 0; pointer-events: none;
  }
  .fader {
    writing-mode: vertical-lr; direction: rtl; width: 24px; height: 120px;
    accent-color: var(--accent); background: transparent; cursor: ns-resize;
  }
  .pads { display: grid; grid-template-columns: repeat(auto-fill, minmax(72px, 1fr)); gap: 6px; margin-top: 12px; }
  .pad, .look {
    min-height: 44px; font-size: 13px; line-height: 1.2; padding: 6px 4px; cursor: pointer;
    color: var(--fg);
    background: linear-gradient(to bottom, color-mix(in srgb, var(--fg) 22%, transparent), color-mix(in srgb, var(--fg) 8%, transparent));
    border: 1px solid color-mix(in srgb, var(--fg) 34%, transparent);
    border-top-color: color-mix(in srgb, var(--fg) 48%, transparent);
    border-radius: 7px;
    box-shadow: inset 0 1px 0 color-mix(in srgb, var(--fg) 22%, transparent), 0 1px 2px rgba(0, 0, 0, 0.25);
  }
  .pad { aspect-ratio: 1; display: flex; align-items: center; justify-content: center; text-align: center; overflow: hidden; }
  .pad.on, .look.on {
    background: linear-gradient(to bottom, color-mix(in srgb, var(--accent) 62%, transparent), color-mix(in srgb, var(--accent) 34%, transparent));
    border-color: color-mix(in srgb, var(--accent) 78%, transparent);
    box-shadow: inset 0 1px 0 color-mix(in srgb, #fff 35%, transparent), 0 0 10px color-mix(in srgb, var(--accent) 45%, transparent);
  }
  .missing { opacity: 0.35; }
  .missing .pill, .missing .knob, .missing .fader, .missing .slider, .missing .menu, .missing .area { pointer-events: none; }
  .tab-scroll { position: relative; margin-bottom: 12px; }
  .tabs {
    display: flex; gap: 2px; overflow-x: auto; scrollbar-width: none;
    border-bottom: 1px solid var(--border); margin-bottom: 0;
  }
  .tabs::-webkit-scrollbar { display: none; }
  .tab {
    display: flex; align-items: center; flex: 0 0 auto;
    background: none; border: none; border-bottom: 2px solid transparent; border-radius: 0;
    padding: 6px 12px; cursor: pointer; color: var(--fg); white-space: nowrap; font-size: 13px;
  }
  .tab.on { color: var(--accent); border-bottom-color: var(--accent); }
  .tab.off { color: var(--fg-muted); opacity: 0.45; }
  .tab-add { color: var(--accent); font-weight: 600; padding-inline: 10px; }
  .tab-arrow {
    position: absolute; top: 0; bottom: 1px; z-index: 1; padding: 0 6px;
    border: none; background: var(--card-bg); color: var(--fg); font-size: 16px; cursor: pointer;
  }
  .tab-arrow[hidden] { display: none; }
  .tab-arrow.left { left: 0; }
  .tab-arrow.right { right: 0; }
  .effect { border-top: 1px solid var(--border); margin-top: 14px; padding-top: 10px; }
  .effect.off { opacity: 0.55; }
  .effect-hd { display: flex; align-items: center; gap: 10px; font-weight: 600; margin-bottom: 8px; }
  .effect-hd .now { font-weight: 400; margin-left: auto; }
  .knobs { display: flex; flex-wrap: wrap; gap: var(--gap); align-items: flex-start; }
  .choices, .field { width: 100%; max-width: 100%; min-width: 0; margin-top: 8px; box-sizing: border-box; }
  .field span, .lab { font-size: 13px; color: var(--fg-muted); }
  .field span { display: block; margin-bottom: 4px; }
  .panel.stack { overflow: visible; width: 100%; height: auto; }
  .line {
    display: flex; align-items: center; gap: 10px; min-width: 0; width: 100%;
    margin-top: 8px; flex-wrap: wrap;
  }
  .lab { flex: 1 1 8em; min-width: 0; overflow-wrap: anywhere; }
  .line .slider { flex: 1 1 120px; width: auto; min-width: 0; }
  .line .now { flex: 0 0 auto; min-width: 3ch; text-align: right; }
  .menu, .area {
    width: 100%; max-width: 100%; box-sizing: border-box;
    background: var(--bg-0); border: 1px solid var(--border); border-radius: 6px;
    padding: 8px 10px; color: var(--fg); color-scheme: dark;
  }
  .area { display: block; resize: vertical; min-height: 4.5em; line-height: 1.35; }
  .layer { margin-top: 16px; }
  .act {
    background: transparent; border: 1px solid var(--border); border-radius: 6px;
    padding: 6px 12px; cursor: pointer; color: var(--fg); white-space: nowrap;
  }
  .act.armed { border-color: var(--accent); color: var(--accent); }
  .add { display: flex; gap: 8px; align-items: center; width: 100%; min-width: 0; margin-top: 10px; flex-wrap: wrap; }
  .add .search, .add .menu { flex: 1 1 140px; width: auto; min-width: 0; margin: 0; }
  .reset {
    flex: 0 0 auto; width: 28px; height: 28px; padding: 0; cursor: pointer;
    background: transparent; border: 1px solid var(--border); border-radius: 6px; color: var(--fg-muted);
  }
  .reset.on { color: var(--accent); border-color: var(--accent); }
  .field .with-reset { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 4px; }
  .field .with-reset span { margin: 0; }
  :focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
`;

class MoonLightCard extends HTMLElement {
  static getConfigForm() {
    return {
      schema: [
        {
          name: "entity",
          required: true,
          selector: { entity: { filter: [{ integration: "moonlight", domain: "light" }] } },
        },
      ],
      computeLabel: (schema) => (schema.name === "entity" ? "MoonLight light" : undefined),
      computeHelper: (schema) =>
        schema.name === "entity"
          ? "The list is MoonLight lights only, one for each device. The card reads the other entities on that device."
          : undefined,
    };
  }

  static getStubConfig(hass) {
    const states = (hass && hass.states) || {};
    const entities = (hass && hass.entities) || {};
    const found = Object.keys(states).find(
      (id) => id.startsWith("light.") && entities[id] && entities[id].platform === "moonlight",
    );
    return { entity: found || "" };
  }

  setConfig(config) {
    this._config = config || {};
    this._html = "";
  }

  set hass(hass) {
    this._hass = hass;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    if (this._gesture) return;
    this._render();
  }

  getGridOptions() {
    return { columns: 6, rows: "auto", min_columns: 3 };
  }

  _hold(active) {
    this._gesture = active;
  }

  _paint(html) {
    if (html === this._html) return false;
    this._html = html;
    this.shadowRoot.innerHTML = html;
    return true;
  }

  // The light state, plus the other entities on its device. Null renders the missing panel.
  _open() {
    const hass = this._hass;
    const entity = this._config && this._config.entity;
    if (!entity) {
      this._paint(`<style>${STYLE}</style><div class="panel">Choose a MoonLight light.</div>`);
      return null;
    }
    const state = hass.states[entity];
    if (!state) {
      this._paint(
        `<style>${STYLE}</style><div class="panel">MoonLight light ${escapeText(entity)} is not available.</div>`,
      );
      return null;
    }
    const found = deviceOf(hass, entity);
    return { hass, entity, state, deviceId: found.deviceId, entries: found.entries };
  }
}

class MoonLightBasicCard extends MoonLightCard {
  getCardSize() {
    return 6;
  }

  _render() {
    const view = this._open();
    if (!view) return;
    const { hass, entity, state, deviceId, entries } = view;
    const root = this.shadowRoot;
    const on = state.state === "on";
    const brightness = lightLevel(state);
    const palettes = state.attributes.effect_list || [];
    const effect = state.attributes.effect || "";
    const query = (this._query || "").toLowerCase();
    const look = lookEntry(entries);
    const looks = look && look.state ? look.state.attributes.options || [] : [];
    const currentLook = look && look.state ? look.state.state : "";
    const shown = palettes.filter((name) => name.toLowerCase().includes(query));
    if (!this._paint(`<style>${STYLE}</style>
      <div class="panel">
        <div class="row">
          <button class="power ${on ? "on" : ""}" title="Power">
            <span class="mark" aria-hidden="true"></span>
            <span class="word">${on ? "On" : "Off"}</span>
          </button>
          <div class="grow">
            <div class="hd tight">Brightness <span class="now level">${brightness}</span></div>
            <input class="slider" type="range" min="0" max="255" value="${brightness}" aria-label="Brightness">
          </div>
        </div>
        <div class="hd">Color palette <span class="now">${escapeText(effect)}</span></div>
        <input class="search" type="text" placeholder="Search palettes" value="${escapeAttr(this._query || "")}" aria-label="Search palettes">
        <div class="list palettes">
          ${shown.map((name) => `<button class="item ${name === effect ? "on" : ""}" data-palette="${escapeAttr(name)}">${escapeText(name)}</button>`).join("")}
        </div>
        <div class="hd">Effect <span class="now">${escapeText(currentLook)}</span></div>
        <div class="looks">
          ${looks.map((name) => `<button class="look ${name === currentLook ? "on" : ""}" data-look="${escapeAttr(name)}">${escapeText(name)}</button>`).join("")}
        </div>
      </div>`)) return;
    root.querySelector(".power").addEventListener("click", () => {
      hass.callService("light", on ? "turn_off" : "turn_on", { entity_id: entity });
    });
    const slider = root.querySelector(".slider");
    const level = root.querySelector(".level");
    slider.addEventListener("pointerdown", () => this._hold(true));
    slider.addEventListener("pointerup", () => this._hold(false));
    slider.addEventListener("pointercancel", () => this._hold(false));
    slider.addEventListener("input", () => {
      level.textContent = slider.value;
    });
    slider.addEventListener("change", () => {
      const value = Number(slider.value);
      if (deviceId) writeControl(hass, deviceId, "fader1", value);
      else hass.callService("light", "turn_on", { entity_id: entity, brightness: value });
    });
    const search = root.querySelector(".search");
    search.addEventListener("input", () => {
      this._query = search.value;
      this._render();
      const next = this.shadowRoot.querySelector(".search");
      if (next) {
        next.focus();
        next.setSelectionRange(next.value.length, next.value.length);
      }
    });
    root.querySelectorAll("[data-palette]").forEach((button) => {
      button.addEventListener("click", () => {
        const name = button.dataset.palette;
        const index = palettes.indexOf(name);
        if (deviceId && index >= 0) writeControl(hass, deviceId, "encoder1", index);
        else hass.callService("light", "turn_on", { entity_id: entity, effect: name });
      });
    });
    root.querySelectorAll("[data-look]").forEach((button) => {
      button.addEventListener("click", () => {
        if (!look) return;
        hass.callService("select", "select_option", { entity_id: look.id, option: button.dataset.look });
      });
    });
  }
}

class MoonLightProCard extends MoonLightCard {
  getCardSize() {
    return 12;
  }

  getGridOptions() {
    return { columns: "full", rows: "auto" };
  }

  _render() {
    const view = this._open();
    if (!view) return;
    const { hass, entity, state, deviceId, entries } = view;
    const root = this.shadowRoot;
    const display = slot(entries, "display");
    const strip = display && display.state ? display.state.state : "MoonLight";
    const palettes = state.attributes.effect_list || [];
    const effect = state.attributes.effect || "";
    const effectIndex = Math.max(0, palettes.indexOf(effect));
    const look = lookEntry(entries);
    const currentLook = look && look.state ? look.state.state : "";
    // Index 1 reads and writes the light. The light has no switch1, encoder1 or fader1 entity.
    const channels = [];
    for (let index = 1; index <= CHANNELS; index += 1) {
      const sw = slot(entries, `switch${index}`);
      const encoder = slot(entries, `encoder${index}`);
      const fader = slot(entries, `fader${index}`);
      const knobLabel = index === 1 ? effect || "Palette" : labelOf(encoder && encoder.state) || `Encoder ${index}`;
      channels.push({
        index,
        on: index === 1 ? state.state === "on" : sw && sw.state && sw.state.state === "on",
        knob: index === 1 ? effectIndex : numberOf(encoder),
        knobMin: index === 1 ? 0 : minOf(encoder, 0),
        knobMax: index === 1 ? Math.max(palettes.length - 1, 0) : maxOf(encoder, 255),
        level: index === 1 ? lightLevel(state) : numberOf(fader),
        levelMax: index === 1 ? 255 : maxOf(fader, 255),
        swLabel: index === 1 ? "Power" : labelOf(sw && sw.state) || `Switch ${index}`,
        knobLabel,
        knobTitle: index === 1 ? `Palette${effect ? ` · ${effect}` : ""}` : knobLabel,
        faderLabel: index === 1 ? "Brightness" : labelOf(fader && fader.state) || `Fader ${index}`,
        swMissing: index !== 1 && !sw,
        encoderMissing: index !== 1 && !encoder,
        faderMissing: index !== 1 && !fader,
      });
    }
    const pads = entries
      .filter((entry) => field(entry, "moonlight") === "pad")
      .sort((a, b) => Number(field(a, "slot")) - Number(field(b, "slot")));
    if (!this._paint(`<style>${STYLE}</style>
      <div class="panel">
        <div class="surface">
          <div class="meter">
            ${segSvg(strip, STRIP_CELLS, true)}
            <div class="bank-name">Switches</div>
            <div class="bank">${channels
              .map(
                (ch) => `<div class="ch ${ch.swMissing ? "missing" : ""}">
                  <button class="pill ${ch.on ? "on" : ""}" data-switch="${ch.index}" title="${escapeAttr(ch.swLabel)}" aria-label="${escapeAttr(ch.swLabel)}"></button>
                  <span class="name" title="${escapeAttr(ch.swLabel)}">${escapeText(ch.swLabel)}</span>
                </div>`,
              )
              .join("")}</div>
            <div class="bank-name">Encoders</div>
            <div class="bank">${channels
              .map((ch) => {
                const span = ch.knobMax - ch.knobMin;
                const frac = span > 0 ? (ch.knob - ch.knobMin) / span : 0;
                return `<div class="ch ${ch.encoderMissing ? "missing" : ""}">
                  <div class="knob" title="Drag up or down, or scroll">${knobSvg(frac)}</div>
                  ${readout(ch.knob)}
                  <span class="name" title="${escapeAttr(ch.knobTitle)}">${escapeText(ch.knobLabel)}</span>
                  <input class="encoder-input" data-encoder="${ch.index}" type="range" min="${ch.knobMin}" max="${ch.knobMax}" value="${ch.knob}" aria-label="${escapeAttr(ch.knobTitle)}">
                </div>`;
              })
              .join("")}</div>
            <div class="bank-name">Faders</div>
            <div class="bank">${channels
              .map(
                (ch) => `<div class="ch ${ch.faderMissing ? "missing" : ""}">
                  <input class="fader" data-fader="${ch.index}" type="range" min="0" max="${ch.levelMax}" value="${ch.level}" aria-label="${escapeAttr(ch.faderLabel)}">
                  ${readout(ch.level)}
                  <span class="name" title="${escapeAttr(ch.faderLabel)}">${escapeText(ch.faderLabel)}</span>
                </div>`,
              )
              .join("")}</div>
          </div>
        </div>
        ${
          pads.length
            ? `<div class="pads">${pads
                .map((pad) => {
                  const name = labelOf(pad.state);
                  return `<button class="pad ${name === currentLook ? "on" : ""}" data-pad="${escapeAttr(pad.id)}">${escapeText(name)}</button>`;
                })
                .join("")}</div>`
            : ""
        }
      </div>`)) return;
    root.querySelectorAll("[data-switch]").forEach((button) => {
      button.addEventListener("click", () => {
        const index = Number(button.dataset.switch);
        if (index === 1) {
          hass.callService("light", state.state === "on" ? "turn_off" : "turn_on", { entity_id: entity });
          return;
        }
        const found = slot(entries, `switch${index}`);
        if (!found || !found.state || found.state.state === "unavailable" || !deviceId) return;
        writeControl(hass, deviceId, `switch${index}`, found.state.state !== "on");
      });
    });
    root.querySelectorAll("[data-encoder]").forEach((input) => {
      const index = Number(input.dataset.encoder);
      const commit = (value) => {
        if (!deviceId) return;
        if (index === 1 && palettes[value]) writeControl(hass, deviceId, "encoder1", value);
        else if (index !== 1) writeControl(hass, deviceId, `encoder${index}`, value);
      };
      input.addEventListener("change", () => commit(Number(input.value)));
      bindKnob(input.parentElement.querySelector(".knob"), input, commit, (active) => this._hold(active));
    });
    root.querySelectorAll("[data-fader]").forEach((input) => {
      input.addEventListener("pointerdown", () => this._hold(true));
      input.addEventListener("pointerup", () => this._hold(false));
      input.addEventListener("pointercancel", () => this._hold(false));
      input.addEventListener("input", () => {
        const cell = input.parentElement.querySelector(".seg-readout");
        if (cell) cell.outerHTML = readout(input.value);
      });
      input.addEventListener("change", () => {
        if (!deviceId) return;
        writeControl(hass, deviceId, `fader${input.dataset.fader}`, Number(input.value));
      });
    });
    root.querySelectorAll("[data-pad]").forEach((button) => {
      button.addEventListener("click", () => {
        hass.callService("button", "press", { entity_id: button.dataset.pad });
      });
    });
  }
}

function finite(value, fallback) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

// The Effects device is the sibling of the light's Control device. The identifier is `{mac}_Effects`.
function effectsDeviceId(hass, controlDeviceId) {
  const devices = hass.devices || {};
  const control = devices[controlDeviceId];
  if (!control || !control.via_device_id) return null;
  const parent = control.via_device_id;
  const ident = (control.identifiers || []).find((pair) => pair && pair[0] === "moonlight");
  const mac = ident ? String(ident[1]).replace(/_Control$/, "") : "";
  const want = mac ? `${mac}_Effects` : "";
  const siblings = Object.keys(devices).filter((id) => devices[id] && devices[id].via_device_id === parent);
  const byId = want
    ? siblings.find((id) =>
        (devices[id].identifiers || []).some((pair) => pair && pair[0] === "moonlight" && pair[1] === want),
      )
    : null;
  if (byId) return byId;
  return (
    siblings.find((id) => (devices[id].name_by_user || devices[id].name) === "Effects") || null
  );
}

function entriesOn(hass, deviceId) {
  const entities = hass.entities || {};
  return Object.keys(entities)
    .filter((id) => entities[id].device_id === deviceId && hass.states[id])
    .map((id) => ({ id, state: hass.states[id] }));
}

function labelFrom(state) {
  const name = (state && state.attributes && state.attributes.friendly_name) || "";
  const at = name.lastIndexOf(" · ");
  return at >= 0 ? name.slice(at + 3) : name;
}

// One layer tab, its own controls, then each effect on that layer. `path` is the cards above the control.
function effectLayers(entries) {
  const layers = new Map();
  for (const entry of entries) {
    const control = field(entry, "control");
    if (!control || (control[0] === "@" && control !== "@status")) continue;
    const path = String(field(entry, "path") || "");
    const parts = path.split(" · ").filter(Boolean);
    if (!parts.length) continue;
    const layerName = parts[0];
    const effectName = parts.slice(1).join(" · ");
    let layer = layers.get(layerName);
    if (!layer) {
      layer = { name: layerName, place: Infinity, controls: [], effects: new Map() };
      layers.set(layerName, layer);
    }
    const place = finite(field(entry, "place"), null);
    const item = { entry, ordinal: finite(field(entry, "ordinal"), 0) };
    if (!effectName) {
      if (place !== null && field(entry, "module") === layerName) layer.place = Math.min(layer.place, place);
      layer.controls.push(item);
    } else {
      let effect = layer.effects.get(effectName);
      if (!effect) {
        effect = { name: effectName, place: place === null ? 0 : place, controls: [] };
        layer.effects.set(effectName, effect);
      } else if (place !== null) {
        effect.place = Math.min(effect.place, place);
      }
      effect.controls.push(item);
    }
  }
  const ordered = [...layers.values()].sort((a, b) => a.place - b.place || a.name.localeCompare(b.name));
  for (const layer of ordered) {
    layer.controls.sort((a, b) => a.ordinal - b.ordinal);
    layer.effectList = [...layer.effects.values()].sort((a, b) => a.place - b.place || a.name.localeCompare(b.name));
    for (const effect of layer.effectList) effect.controls.sort((a, b) => a.ordinal - b.ordinal);
  }
  return ordered;
}

function takeControl(controls, name) {
  const index = controls.findIndex((item) => field(item.entry, "control") === name);
  if (index < 0) return null;
  return controls.splice(index, 1)[0];
}

function effectHead(title, enabled, status, moduleName) {
  const on = enabled && enabled.entry.state && enabled.entry.state.state === "on";
  const pill = enabled
    ? `<button class="pill ${on ? "on" : ""}" data-switch-entity="${escapeAttr(enabled.entry.id)}" title="Enabled" aria-label="Enabled"></button>`
    : "";
  const line = status && status.entry.state ? `<span class="now">${escapeText(status.entry.state.state)}</span>` : "";
  const remove = moduleName
    ? `<button class="act" type="button" data-remove="${escapeAttr(moduleName)}" aria-label="Delete ${escapeAttr(title)}">Delete</button>`
    : "";
  return `<div class="effect-hd"><span class="grow">${escapeText(title)}</span>${line}${pill}${remove}</div>`;
}

function effectCatalog(entries) {
  const found = entries.find(
    (entry) => entry.state && entry.state.attributes && Array.isArray(entry.state.attributes.effect_types),
  );
  if (!found) return { types: [], layerType: "Layer", defaults: {} };
  const defaults = found.state.attributes.defaults;
  return {
    types: found.state.attributes.effect_types,
    layerType: found.state.attributes.layer_type || "Layer",
    defaults: defaults && typeof defaults === "object" ? defaults : {},
  };
}

function moduleTypeOf(controls) {
  const found = controls.find((item) => field(item.entry, "module_type"));
  return found ? String(field(found.entry, "module_type")) : "";
}

function replaceMenu(moduleName, typeName, types) {
  const current = types.find((item) => item.type === typeName);
  const choices = current ? types.filter((item) => item.role === current.role) : [];
  if (!typeName || choices.length < 2) return "";
  const options = choices
    .map((item) => `<option value="${escapeAttr(item.type)}"${item.type === typeName ? " selected" : ""}>${escapeText(item.name)}</option>`)
    .join("");
  return `<label class="field"><span>Replace</span><select class="menu" data-replace="${escapeAttr(moduleName)}" data-current="${escapeAttr(typeName)}" aria-label="Replace ${escapeAttr(moduleName)}">${options}</select></label>`;
}

function addEffectRow(parent, types, clearName) {
  const clear = clearName
    ? `<button class="act" type="button" data-clear="${escapeAttr(clearName)}" aria-label="Clear ${escapeAttr(clearName)}">Clear</button>`
    : "";
  if (!types.length) {
    return `<div class="add"><p class="lab">This MoonLight has not listed its effect types.</p>${clear}</div>`;
  }
  const options = types
    .map((item) => `<option value="${escapeAttr(item.type)}">${escapeText(item.name)}</option>`)
    .join("");
  return `<div class="add">
    <input class="search" data-filter="${escapeAttr(parent)}" placeholder="Search effects" aria-label="Search effects">
    <select class="menu" data-effect-type="${escapeAttr(parent)}" aria-label="Effect type">${options}</select>
    <button class="act" type="button" data-add-effect="${escapeAttr(parent)}">Add</button>
    ${clear}
  </div>`;
}

function controlDefault(item, defaults) {
  const typeName = String(field(item.entry, "module_type") || "");
  const control = String(field(item.entry, "control") || "");
  const table = defaults && defaults[typeName];
  if (!table || !Object.prototype.hasOwnProperty.call(table, control)) return undefined;
  return table[control];
}

function resetButton(item, defaults) {
  const raw = controlDefault(item, defaults);
  if (raw === undefined) return "";
  const entry = item.entry;
  const state = entry.state;
  const domain = entry.id.split(".", 1)[0];
  const label = labelFrom(state);
  const options = (state && state.attributes && state.attributes.options) || [];
  const value = domain === "select" && typeof raw === "number" && options[raw] !== undefined ? options[raw] : raw;
  const current = state ? state.state : "";
  let same = String(current) === String(value);
  if (domain === "switch") same = (current === "on") === Boolean(value);
  else if (domain === "number") same = finite(current, NaN) === Number(value);
  return `<button class="reset${same ? "" : " on"}" type="button" data-reset="${escapeAttr(entry.id)}" data-reset-domain="${domain}" data-reset-value="${escapeAttr(JSON.stringify(value))}" aria-label="Reset ${escapeAttr(label)}">↺</button>`;
}

function effectControl(item, defaults) {
  const entry = item.entry;
  const state = entry.state;
  const domain = entry.id.split(".", 1)[0];
  const kind = String(field(entry, "kind") || "");
  const label = labelFrom(state);
  const missing = !state || state.state === "unavailable" || state.state === "unknown";
  const dim = missing ? " missing" : "";
  const reset = resetButton(item, defaults);
  if (domain === "number") {
    const min = finite(state && state.attributes.min, 0);
    const max = finite(state && state.attributes.max, 255);
    const value = missing ? min : finite(state.state, min);
    return `<div class="line${dim}">
      <span class="lab">${escapeText(label)}</span>
      <input class="slider" type="range" min="${min}" max="${max}" value="${Math.round(value)}" data-number="${escapeAttr(entry.id)}" aria-label="${escapeAttr(label)}">
      <span class="now level">${escapeText(Math.round(value))}</span>
      ${reset}
    </div>`;
  }
  if (domain === "switch") {
    const on = state && state.state === "on";
    return `<div class="line${dim}"><span class="lab">${escapeText(label)}</span><button class="pill ${on ? "on" : ""}" data-switch-entity="${escapeAttr(entry.id)}" aria-label="${escapeAttr(label)}"></button>${reset}</div>`;
  }
  if (domain === "select") {
    const options = (state && state.attributes.options) || [];
    const current = state ? state.state : "";
    const names = options.includes(current) || !current ? options : options.concat(current);
    return `<label class="field${dim}"><span class="with-reset"><span>${escapeText(label)}</span>${reset}</span><select class="menu" data-select="${escapeAttr(entry.id)}" aria-label="${escapeAttr(label)}">${names
      .map((option) => `<option value="${escapeAttr(option)}"${option === current ? " selected" : ""}>${escapeText(option)}</option>`)
      .join("")}</select></label>`;
  }
  if (domain === "text") {
    const value = !state || state.state === "unknown" || state.state === "unavailable" ? "" : state.state;
    const multi = kind === "textarea" || value.includes("\n");
    if (multi) {
      const rows = Math.min(12, Math.max(3, value.split("\n").length));
      return `<label class="field${dim}"><span class="with-reset"><span>${escapeText(label)}</span>${reset}</span><textarea class="area" rows="${rows}" data-text="${escapeAttr(entry.id)}" aria-label="${escapeAttr(label)}">${escapeText(value)}</textarea></label>`;
    }
    return `<label class="field${dim}"><span class="with-reset"><span>${escapeText(label)}</span>${reset}</span><input class="search" data-text="${escapeAttr(entry.id)}" value="${escapeAttr(value)}" aria-label="${escapeAttr(label)}"></label>`;
  }
  if (domain === "button") {
    return `<button class="pad" data-press="${escapeAttr(entry.id)}">${escapeText(label)}</button>`;
  }
  if (domain === "sensor" && state) {
    return `<div class="line"><span class="lab">${escapeText(label)}</span><span class="now">${escapeText(state.state)}</span></div>`;
  }
  return "";
}

function effectBody(controls, defaults) {
  const own = controls.slice();
  const enabled = takeControl(own, "enabled");
  const status = takeControl(own, "@status");
  return { enabled, status, html: own.map((item) => effectControl(item, defaults)).join("") };
}

function numberOf(entry) {
  if (!entry || !entry.state || entry.state.state === "unavailable" || entry.state.state === "unknown") return 0;
  const value = Number(entry.state.state);
  return Number.isFinite(value) ? value : 0;
}

function limitOf(entry, key, fallback) {
  const value = entry && entry.state && entry.state.attributes[key];
  return Number.isFinite(value) ? value : fallback;
}

function minOf(entry, fallback) {
  return limitOf(entry, "min", fallback);
}

function maxOf(entry, fallback) {
  return limitOf(entry, "max", fallback);
}

function escapeText(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function escapeAttr(value) {
  return escapeText(value).replace(/"/g, "&quot;");
}

class MoonLightEffectsCard extends MoonLightCard {
  getCardSize() {
    return this._rows || 12;
  }

  getGridOptions() {
    return { columns: "full", rows: "auto" };
  }

  static getConfigForm() {
    const form = super.getConfigForm();
    form.computeHelper = (schema) =>
      schema.name === "entity"
        ? "The list is MoonLight lights only, one for each device. The card reads the Effects device of that MoonLight."
        : undefined;
    return form;
  }

  _render() {
    const view = this._open();
    if (!view) return;
    const { hass } = view;
    const root = this.shadowRoot;
    const effectsId = effectsDeviceId(hass, view.deviceId);
    if (!effectsId) {
      this._paint(
        `<style>${STYLE}</style><div class="panel">Effects is off for this MoonLight device. Turn it on in the integration options.</div>`,
      );
      return;
    }
    const entries = entriesOn(hass, effectsId);
    const layers = effectLayers(entries);
    const catalog = effectCatalog(entries);
    const effectsDevice = hass.devices[effectsId];
    const effectsName = (effectsDevice && effectsDevice.name) || "Effects";
    const names = layers.map((layer) => layer.name);
    if (this._seen) {
      const added = names.filter((name) => !this._seen.includes(name));
      if (added.length) this._layer = added[added.length - 1];
    }
    this._seen = names;
    const active = names.includes(this._layer) ? this._layer : names[0];
    this._layer = active;
    const layer = layers.find((item) => item.name === active);
    const layerBody = layer ? effectBody(layer.controls, catalog.defaults) : { enabled: null, status: null, html: "" };
    const effects = layer
      ? layer.effectList
          .map((effect) => {
            const effectControls = effectBody(effect.controls, catalog.defaults);
            const off = effectControls.enabled && effectControls.enabled.entry.state && effectControls.enabled.entry.state.state !== "on";
            const replace = replaceMenu(effect.name, moduleTypeOf(effect.controls), catalog.types);
            return `<section class="effect${off ? " off" : ""}">${effectHead(effect.name, effectControls.enabled, effectControls.status, effect.name)}${replace}${effectControls.html}</section>`;
          })
          .join("")
      : "";
    const shown = layer ? layer.controls.length + layer.effectList.reduce((count, effect) => count + effect.controls.length + 1, 0) + 3 : 4;
    this._rows = Math.max(6, shown);
    const tabs = layers
      .map((item) => {
        const enabled = item.controls.find((control) => field(control.entry, "control") === "enabled");
        const off = enabled && enabled.entry.state && enabled.entry.state.state !== "on";
        return `<button class="tab${item.name === active ? " on" : ""}${off ? " off" : ""}" type="button" role="tab" data-layer="${escapeAttr(item.name)}" aria-selected="${item.name === active ? "true" : "false"}">${escapeText(item.name)}</button>`;
      })
      .join("");
    const panel = layer
      ? `${effectHead(layer.name, layerBody.enabled, layerBody.status, layer.name)}${replaceMenu(layer.name, moduleTypeOf(layer.controls), catalog.types)}${layerBody.html}${effects}${addEffectRow(layer.name, catalog.types, layer.effectList.length ? layer.name : "")}`
      : `<p class="lab">This MoonLight device has no effect layers.</p>`;
    if (
      !this._paint(`<style>${STYLE}</style>
      <div class="panel stack">
        <div class="tab-scroll">
          <button class="tab-arrow left" type="button" data-tab-dir="-1" aria-label="Earlier layers" hidden>‹</button>
          <div class="tabs" role="tablist">
            ${tabs}
            <button class="tab tab-add" type="button" data-add-layer="${escapeAttr(catalog.layerType)}" aria-label="Add layer">+</button>
          </div>
          <button class="tab-arrow right" type="button" data-tab-dir="1" aria-label="Later layers" hidden>›</button>
        </div>
        ${panel}
      </div>`)
    )
      return;
    const strip = root.querySelector(".tabs");
    const earlier = root.querySelector("[data-tab-dir='-1']");
    const later = root.querySelector("[data-tab-dir='1']");
    const placeArrows = () => {
      earlier.hidden = strip.scrollLeft <= 1;
      later.hidden = strip.scrollLeft + strip.clientWidth >= strip.scrollWidth - 1;
    };
    strip.addEventListener("scroll", placeArrows, { passive: true });
    earlier.addEventListener("click", () => strip.scrollBy({ left: -strip.clientWidth * 0.8, behavior: "smooth" }));
    later.addEventListener("click", () => strip.scrollBy({ left: strip.clientWidth * 0.8, behavior: "smooth" }));
    if (typeof ResizeObserver === "function") new ResizeObserver(placeArrows).observe(strip);
    placeArrows();
    root.querySelectorAll("[data-layer]").forEach((button) => {
      button.addEventListener("click", () => {
        this._layer = button.dataset.layer;
        this._html = "";
        this._render();
      });
    });
    root.querySelectorAll("[data-add-layer]").forEach((button) => {
      button.addEventListener("click", () => {
        hass.callService("moonlight", "add_module", {
          device_id: effectsId,
          type: button.dataset.addLayer,
          parent: effectsName,
        });
      });
    });
    root.querySelectorAll("[data-add-effect]").forEach((button) => {
      button.addEventListener("click", () => {
        const menu = button.parentElement.querySelector("select");
        if (!menu || !menu.value) return;
        hass.callService("moonlight", "add_module", {
          device_id: effectsId,
          type: menu.value,
          parent: button.dataset.addEffect,
        });
      });
    });
    root.querySelectorAll("[data-filter]").forEach((input) => {
      input.addEventListener("input", () => {
        const menu = input.parentElement.querySelector("select");
        const query = input.value.trim().toLowerCase();
        let first = "";
        [...menu.options].forEach((option) => {
          const show = !query || option.text.toLowerCase().includes(query);
          option.hidden = !show;
          if (show && !first) first = option.value;
        });
        if (menu.selectedOptions[0] && menu.selectedOptions[0].hidden && first) menu.value = first;
      });
    });
    root.querySelectorAll("select[data-replace]").forEach((menu) => {
      menu.addEventListener("change", () => {
        if (!menu.value || menu.value === menu.dataset.current) return;
        hass.callService("moonlight", "replace_module", {
          device_id: effectsId,
          module: menu.dataset.replace,
          type: menu.value,
        });
      });
    });
    root.querySelectorAll("[data-clear]").forEach((button) => {
      button.addEventListener("click", () => {
        if (button.dataset.armed !== "1") {
          button.dataset.armed = "1";
          button.textContent = "Confirm";
          button.classList.add("armed");
          window.setTimeout(() => {
            if (!button.isConnected) return;
            button.dataset.armed = "";
            button.textContent = "Clear";
            button.classList.remove("armed");
          }, 3000);
          return;
        }
        hass.callService("moonlight", "clear_children", { device_id: effectsId, module: button.dataset.clear });
      });
    });
    root.querySelectorAll("[data-reset]").forEach((button) => {
      button.addEventListener("click", () => {
        const id = button.dataset.reset;
        const value = JSON.parse(button.dataset.resetValue);
        const domain = button.dataset.resetDomain;
        if (domain === "number") hass.callService("number", "set_value", { entity_id: id, value: Number(value) });
        else if (domain === "switch") hass.callService("switch", value ? "turn_on" : "turn_off", { entity_id: id });
        else if (domain === "select") hass.callService("select", "select_option", { entity_id: id, option: String(value) });
        else if (domain === "text") hass.callService("text", "set_value", { entity_id: id, value: String(value) });
      });
    });
    root.querySelectorAll("[data-remove]").forEach((button) => {
      button.addEventListener("click", () => {
        if (button.dataset.armed !== "1") {
          button.dataset.armed = "1";
          button.textContent = "Confirm";
          button.classList.add("armed");
          window.setTimeout(() => {
            if (!button.isConnected) return;
            button.dataset.armed = "";
            button.textContent = "Delete";
            button.classList.remove("armed");
          }, 3000);
          return;
        }
        hass.callService("moonlight", "remove_module", {
          device_id: effectsId,
          module: button.dataset.remove,
        });
      });
    });
    root.querySelectorAll("[data-switch-entity]").forEach((button) => {
      button.addEventListener("click", () => {
        const id = button.dataset.switchEntity;
        const state = hass.states[id];
        if (!state || state.state === "unavailable") return;
        hass.callService("switch", state.state === "on" ? "turn_off" : "turn_on", { entity_id: id });
      });
    });
    root.querySelectorAll("[data-number]").forEach((input) => {
      input.addEventListener("pointerdown", () => this._hold(true));
      input.addEventListener("pointerup", () => this._hold(false));
      input.addEventListener("pointercancel", () => this._hold(false));
      input.addEventListener("input", () => {
        const level = input.parentElement.querySelector(".level");
        if (level) level.textContent = input.value;
      });
      input.addEventListener("change", () => {
        hass.callService("number", "set_value", { entity_id: input.dataset.number, value: Number(input.value) });
      });
    });
    root.querySelectorAll("select[data-select]").forEach((menu) => {
      menu.addEventListener("change", () => {
        hass.callService("select", "select_option", { entity_id: menu.dataset.select, option: menu.value });
      });
    });
    root.querySelectorAll("[data-text]").forEach((input) => {
      input.addEventListener("focus", () => this._hold(true));
      input.addEventListener("input", () => {
        if (input.tagName !== "TEXTAREA") return;
        input.rows = Math.min(12, Math.max(3, input.value.split("\n").length));
      });
      input.addEventListener("blur", () => {
        this._hold(false);
        hass.callService("text", "set_value", { entity_id: input.dataset.text, value: input.value });
      });
    });
    root.querySelectorAll("[data-press]").forEach((button) => {
      button.addEventListener("click", () => {
        hass.callService("button", "press", { entity_id: button.dataset.press });
      });
    });
  }
}

if (!customElements.get(BASIC)) customElements.define(BASIC, MoonLightBasicCard);
if (!customElements.get(PRO)) customElements.define(PRO, MoonLightProCard);
if (!customElements.get(EFFECTS)) customElements.define(EFFECTS, MoonLightEffectsCard);

window.customCards = window.customCards || [];
window.customCards.push(
  {
    type: BASIC,
    name: "MoonLight Basic",
    preview: true,
    description: "Power, brightness, palette and effect looks.",
  },
  {
    type: PRO,
    name: "MoonLight Pro",
    preview: true,
    description: "The Control desk: display, switches, encoders, faders and preset pads.",
  },
  {
    type: EFFECTS,
    name: "MoonLight Effects",
    preview: true,
    description: "The Effects page: one tab per layer. The open layer holds its effects.",
  },
);
