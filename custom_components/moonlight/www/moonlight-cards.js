// MoonLight Lovelace cards. Basic is power, brightness, palette and looks.
// Pro is the Control desk: display strip, switches, encoder dials, faders and preset pads.
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
  // device_id is the target. It is also in the data, because the service schema requires it
  // and an older frontend leaves a target field where the caller put it.
  const data = {
    device_id: deviceId,
    module: "Control",
    control,
    value: JSON.stringify(value),
  };
  hass.callService("moonlight", "set_control", data, { device_id: deviceId });
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
  .list { max-height: 240px; overflow: auto; margin-top: 8px; }
  .item {
    display: block; width: 100%; text-align: left; background: transparent;
    border: 0; border-bottom: 1px solid var(--border); padding: 10px 8px;
    font-size: 15px; cursor: pointer;
  }
  .item.on { background: var(--card-bg-2); box-shadow: inset 2px 0 0 var(--accent); }
  .looks { display: grid; grid-template-columns: repeat(auto-fill, minmax(96px, 1fr)); gap: 6px; }
  .surface { overflow-x: auto; max-width: 100%; min-width: 0; }
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
  .missing .pill, .missing .knob, .missing .fader { pointer-events: none; }
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
    const brightness = Number(state.attributes.brightness ?? 0);
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
        level: index === 1 ? Number(state.attributes.brightness ?? 0) : numberOf(fader),
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

if (!customElements.get(BASIC)) customElements.define(BASIC, MoonLightBasicCard);
if (!customElements.get(PRO)) customElements.define(PRO, MoonLightProCard);

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
);
