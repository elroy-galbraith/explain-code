// Reusable minimal DOM stub for running a micro-world's <script> block inside
// node:vm. Shared by every verification harness so the stub itself is tested
// once instead of hand-retyped (and silently drifting) per build.
// See references/engine.md for the harness pattern this supports.

export function extractScript(html) {
  // Non-greedy: a self-contained micro-world should have one <script> block,
  // but a greedy match would silently span first-open to last-close if a
  // second inline block (e.g. analytics) is ever added.
  const m = html.match(/<script>([\s\S]*?)<\/script>/);
  if (!m) throw new Error("no <script> block found");
  return m[1];
}

export function makeElement() {
  const el = {
    _html: "", _attrs: new Map(), hidden: false, textContent: "",
    style: {}, dataset: {},
    classList: { add(){}, remove(){}, toggle(){} },
    addEventListener(){}, setAttribute(k, v){ this._attrs.set(k, String(v)); },
    getAttribute(k){ return this._attrs.get(k) ?? null; },
    querySelectorAll(){ return []; },
    appendChild(){}, closest(){ return null; },
  };
  Object.defineProperty(el, "innerHTML", {
    get(){ return this._html; },
    set(v){
      this._html = v;
      // crude sanity: flag unbalanced span/div/table tags
      for (const tag of ["div", "span", "table", "tr", "td", "th", "button", "pre", "details"]) {
        const open = (v.match(new RegExp(`<${tag}[\\s>]`, "g")) || []).length;
        const close = (v.match(new RegExp(`</${tag}>`, "g")) || []).length;
        if (open !== close) throw new Error(`unbalanced <${tag}> (${open} open / ${close} close) in innerHTML: ${v.slice(0, 120)}...`);
      }
      if (v.includes("undefined") || v.includes("NaN")) {
        throw new Error(`suspicious 'undefined'/'NaN' in innerHTML: ...${v.slice(Math.max(0, v.search(/undefined|NaN/) - 80), v.search(/undefined|NaN/) + 40)}...`);
      }
    },
  });
  return el;
}

export function makeDocument() {
  const els = new Map();
  return {
    querySelector(sel){ if (!els.has(sel)) els.set(sel, makeElement()); return els.get(sel); },
    querySelectorAll(){ return []; },
    addEventListener(){}, createElement(){ return makeElement(); }, createTextNode(t){ return { t }; },
  };
}

// Base vm sandbox: a document stub, a minimal window, and timers that never
// fire (autoplay's setTimeout chain is inert under the harness). Pass
// overrides for anything a specific build's script also touches globally.
export function baseSandbox(overrides = {}) {
  return {
    document: makeDocument(),
    window: { innerWidth: 1280, innerHeight: 800 },
    console, clearTimeout, setTimeout: () => 0,
    ...overrides,
  };
}
