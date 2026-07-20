#!/usr/bin/env python3
"""
render.py — turn an explain-diff JSON spec into a single self-contained HTML page.

Why this exists
---------------
The CSS, quiz JavaScript, and page scaffolding are identical on every run of the
explain-diff skill. Only the *content* (prose, diagrams, questions) changes per
diff. Having the model hand-write the boilerplate each time wastes tokens and
invites malformed-HTML bugs. So the model emits a compact JSON spec and this
script renders it deterministically.

It also owns two things the model is bad at:
  1. Answer-position shuffling. LLMs are poor RNGs and drift to the same slot.
     Here every option carries a `correct` flag and positions are shuffled at
     render time with a per-question seed, so correct answers spread across all
     positions and stay stable on reload.
  2. The adaptive "test-first" gate + progressive disclosure wiring, so behaviour
     is consistent no matter what the model wrote.

Usage
-----
    python3 render.py spec.json -o out.html
    cat spec.json | python3 render.py -           # read stdin, write stdout

Spec schema (see SKILL.md for the authoritative version)
--------------------------------------------------------
{
  "title": "Rate limiter migration",
  "subtitle": "PR #482 · auth-service",          # optional
  "slug": "2026-07-20-rate-limiter",              # used for filename + shuffle seed
  "gate": [                                        # 2-3 quick diagnostic questions
    {"prompt": "...", "options": [
        {"text": "...", "correct": true},
        {"text": "...", "correct": false}
     ], "explanation": "..."}
  ],
  "sections": [
    {"id": "background", "heading": "Background",
     "summary": "2-3 sentence TL;DR, always visible",
     "body": "<p>Deep, beginner-friendly HTML, hidden behind a toggle.</p>"}
  ],
  "quiz": [                                         # 5 medium questions (the post-test)
    {"prompt": "...", "options": [ ... ], "explanation": "..."}
  ]
}
"""

import argparse
import html
import json
import random
import sys


# --------------------------------------------------------------------------- #
# Content processing
# --------------------------------------------------------------------------- #

def _seeded_shuffle(options, seed):
    """Return options in a shuffled order using a deterministic per-question seed.

    Deterministic so the same spec always renders identically (stable on reload,
    reproducible in review), while still spreading the correct answer across all
    positions instead of pinning it to one slot.
    """
    rng = random.Random(seed)
    shuffled = list(options)
    rng.shuffle(shuffled)
    return shuffled


def _normalize_question(q, seed):
    """Validate a question, shuffle its options, and record the correct index."""
    prompt = q.get("prompt", "").strip()
    options = q.get("options", [])
    if not prompt:
        raise ValueError("A question is missing its 'prompt'.")
    if len(options) < 2:
        raise ValueError(f"Question {prompt!r} needs at least 2 options.")
    if sum(1 for o in options if o.get("correct")) != 1:
        raise ValueError(
            f"Question {prompt!r} must have exactly one option with correct=true."
        )

    shuffled = _seeded_shuffle(options, seed)
    correct_index = next(i for i, o in enumerate(shuffled) if o.get("correct"))
    return {
        "prompt": prompt,
        "options": [o.get("text", "").strip() for o in shuffled],
        "correct_index": correct_index,
        "explanation": (q.get("explanation") or "").strip(),
    }


def _process(spec):
    slug = spec.get("slug", "explanation")
    gate = [
        _normalize_question(q, seed=f"{slug}:gate:{i}")
        for i, q in enumerate(spec.get("gate", []))
    ]
    quiz = [
        _normalize_question(q, seed=f"{slug}:quiz:{i}")
        for i, q in enumerate(spec.get("quiz", []))
    ]
    sections = []
    for i, s in enumerate(spec.get("sections", [])):
        sections.append({
            "id": s.get("id") or f"section-{i}",
            "heading": s.get("heading", f"Section {i + 1}").strip(),
            "summary": (s.get("summary") or "").strip(),
            "body": s.get("body", ""),  # raw HTML, intentionally not escaped
        })
    return {
        "title": spec.get("title", "Change explanation").strip(),
        "subtitle": (spec.get("subtitle") or "").strip(),
        "slug": slug,
        "gate": gate,
        "sections": sections,
        "quiz": quiz,
    }


# --------------------------------------------------------------------------- #
# HTML fragments
# --------------------------------------------------------------------------- #

def _render_question(q, block, idx):
    """Render one question. `block` is 'gate' or 'quiz' (used for element ids)."""
    e = html.escape
    opts = "\n".join(
        f'''        <li>
          <label class="option">
            <input type="radio" name="{block}-{idx}" value="{oi}">
            <span>{e(text)}</span>
          </label>
        </li>'''
        for oi, text in enumerate(q["options"])
    )
    explanation = (
        f'      <div class="explanation" hidden>{e(q["explanation"])}</div>'
        if q["explanation"] else ""
    )
    return f'''    <div class="question" data-correct="{q["correct_index"]}">
      <p class="prompt">{e(q["prompt"])}</p>
      <ul class="options">
{opts}
      </ul>
{explanation}
      <div class="verdict" hidden></div>
    </div>'''


def _render_sections(sections):
    e = html.escape
    out = []
    for s in sections:
        summary = f'<p class="section-summary">{e(s["summary"])}</p>' if s["summary"] else ""
        out.append(f'''  <section id="{e(s["id"])}" class="doc-section">
    <h2>{e(s["heading"])}</h2>
    {summary}
    <details class="deep">
      <summary>Show the full walkthrough</summary>
      <div class="deep-body">
{s["body"]}
      </div>
    </details>
  </section>''')
    return "\n".join(out)


def _render_toc(sections):
    e = html.escape
    items = "\n".join(
        f'    <li><a href="#{e(s["id"])}">{e(s["heading"])}</a></li>'
        for s in sections
    )
    return f'  <nav class="toc"><strong>Contents</strong>\n  <ul>\n{items}\n  </ul>\n  </nav>'


# --------------------------------------------------------------------------- #
# Page template
# --------------------------------------------------------------------------- #

CSS = """
  :root{
    --bg:#ffffff;--fg:#1a1a1a;--muted:#5c6670;--line:#e3e6ea;
    --accent:#2563eb;--ok:#16a34a;--bad:#dc2626;--card:#f7f8fa;--radius:10px;
  }
  @media (prefers-color-scheme:dark){
    :root{--bg:#0f1115;--fg:#e6e8eb;--muted:#9aa4af;--line:#262b33;
      --accent:#60a5fa;--ok:#4ade80;--bad:#f87171;--card:#161a20;}
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--fg);
    font:16px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;}
  .wrap{max-width:820px;margin:0 auto;padding:40px 24px 96px;}
  header.page{border-bottom:1px solid var(--line);padding-bottom:20px;margin-bottom:8px;}
  header.page h1{font-size:1.9rem;margin:0 0 4px;letter-spacing:-0.01em;}
  header.page .subtitle{color:var(--muted);margin:0;}
  h2{font-size:1.35rem;margin:2.2em 0 .4em;letter-spacing:-0.01em;}
  a{color:var(--accent);text-decoration:none} a:hover{text-decoration:underline}
  .toc{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);
    padding:14px 18px;margin:22px 0;font-size:.94rem;}
  .toc ul{margin:.4em 0 0;padding-left:1.1em;} .toc li{margin:.15em 0;}
  .section-summary{font-size:1.02rem;}
  details.deep{border:1px solid var(--line);border-radius:var(--radius);
    background:var(--card);padding:0 16px;margin:.6em 0;}
  details.deep>summary{cursor:pointer;padding:12px 0;font-weight:600;color:var(--accent);
    list-style:none;}
  details.deep>summary::-webkit-details-marker{display:none}
  details.deep>summary::before{content:"▸ ";}
  details.deep[open]>summary::before{content:"▾ ";}
  .deep-body{padding:4px 0 16px;border-top:1px solid var(--line);margin-top:0;}
  pre{white-space:pre-wrap;background:var(--card);border:1px solid var(--line);
    border-radius:var(--radius);padding:14px 16px;overflow-x:auto;font-size:.88rem;
    font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;}
  code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:.9em;}
  .card{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);
    padding:20px 22px;margin:18px 0;}
  .gate-banner{border-left:4px solid var(--accent);}
  .question{padding:14px 0;border-top:1px solid var(--line);}
  .question:first-of-type{border-top:none}
  .prompt{font-weight:600;margin:.2em 0 .6em;}
  .options{list-style:none;margin:0;padding:0;}
  .option{display:flex;gap:10px;align-items:flex-start;padding:8px 10px;border-radius:8px;
    cursor:pointer;} .option:hover{background:rgba(127,127,127,.08)}
  .option input{margin-top:4px}
  .question.answered .option{cursor:default}
  .option.correct{background:rgba(22,163,74,.14);}
  .option.wrong{background:rgba(220,38,38,.14);}
  .verdict{margin:.5em 0 .2em;font-weight:600;}
  .verdict.pass{color:var(--ok)} .verdict.fail{color:var(--bad)}
  .explanation{color:var(--muted);font-size:.94rem;margin:.3em 0 .2em;
    border-left:3px solid var(--line);padding-left:12px;}
  button{font:inherit;font-weight:600;background:var(--accent);color:#fff;border:0;
    border-radius:8px;padding:9px 16px;cursor:pointer;} button:hover{filter:brightness(1.06)}
  button.secondary{background:transparent;color:var(--accent);border:1px solid var(--accent);}
  .row{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-top:14px;}
  .muted{color:var(--muted);font-size:.94rem;}
  #deep-content[hidden]{display:none}
  .pill{display:inline-block;font-size:.78rem;font-weight:700;padding:2px 9px;border-radius:999px;
    background:var(--accent);color:#fff;vertical-align:middle;}
"""

JS = """
  // Grade a block of questions. Returns [correctCount, total].
  function gradeBlock(root){
    const qs = [...root.querySelectorAll('.question')];
    let correct = 0;
    for(const q of qs){
      const want = +q.dataset.correct;
      const picked = q.querySelector('input:checked');
      const opts = [...q.querySelectorAll('.option')];
      q.classList.add('answered');
      opts.forEach((o,i)=>{
        const input = o.querySelector('input'); input.disabled = true;
        if(i===want) o.classList.add('correct');
        else if(input.checked) o.classList.add('wrong');
      });
      const exp = q.querySelector('.explanation'); if(exp) exp.hidden = false;
      const v = q.querySelector('.verdict');
      const got = picked && +picked.value===want;
      if(got){correct++; v.textContent='Correct'; v.className='verdict pass';}
      else{v.textContent = picked? 'Not quite' : 'No answer'; v.className='verdict fail';}
      v.hidden = false;
    }
    return [correct, qs.length];
  }

  function revealDeep(open){
    const dc = document.getElementById('deep-content');
    if(dc) dc.hidden = false;
    if(open) document.querySelectorAll('details.deep').forEach(d=>d.open=true);
    const toc = document.querySelector('.toc'); if(toc) toc.hidden = false;
  }

  document.addEventListener('DOMContentLoaded', ()=>{
    const gateForm = document.getElementById('gate');
    const gateBtn = document.getElementById('gate-check');
    if(gateBtn){
      gateBtn.addEventListener('click', ()=>{
        const [c,t] = gradeBlock(gateForm);
        const res = document.getElementById('gate-result');
        const passed = c===t;
        // Passed the gate -> you already know this. Keep the deep dive collapsed.
        // Missed one   -> reveal everything, expanded, so you can read up.
        revealDeep(!passed);
        res.hidden = false;
        res.className = 'verdict ' + (passed?'pass':'fail');
        res.textContent = passed
          ? `You got ${c}/${t}. You already have a solid grasp — the walkthrough below is collapsed. Expand any part you want, or jump to the final quiz.`
          : `You got ${c}/${t}. No problem — the full walkthrough is expanded below. The quiz at the end confirms it stuck.`;
        gateBtn.hidden = true;
        document.getElementById('gate-skip').hidden = true;
      });
    }
    const skip = document.getElementById('gate-skip');
    if(skip) skip.addEventListener('click', ()=>{ revealDeep(true); skip.closest('.row').hidden = true; });

    const quizBtn = document.getElementById('quiz-check');
    if(quizBtn){
      quizBtn.addEventListener('click', ()=>{
        const [c,t] = gradeBlock(document.getElementById('quiz'));
        const res = document.getElementById('quiz-result');
        res.hidden = false;
        res.className = 'verdict ' + (c===t?'pass':'fail');
        res.textContent = `You scored ${c}/${t}.`;
        quizBtn.hidden = true;
      });
    }
  });
"""


def render(spec):
    data = _process(spec)
    e = html.escape

    subtitle = f'<p class="subtitle">{e(data["subtitle"])}</p>' if data["subtitle"] else ""

    gate_html = ""
    if data["gate"]:
        gate_qs = "\n".join(
            _render_question(q, "gate", i) for i, q in enumerate(data["gate"])
        )
        gate_html = f'''<div class="card gate-banner" id="gate-card">
  <p><span class="pill">Start here</span> &nbsp;Already familiar with this change? Take this {len(data["gate"])}-question check. Ace it and you can skip straight to the quiz; miss one and the full walkthrough opens up.</p>
  <div id="gate">
{gate_qs}
  </div>
  <div id="gate-result" class="verdict" hidden></div>
  <div class="row">
    <button id="gate-check">Check my understanding</button>
    <button id="gate-skip" class="secondary">Skip the check, show me everything</button>
  </div>
</div>'''

    # If there's no gate, deep content is visible by default.
    deep_hidden = " hidden" if data["gate"] else ""
    toc = _render_toc(data["sections"]) if data["sections"] else ""
    toc_hidden = toc.replace('<nav class="toc"', '<nav class="toc" hidden', 1) if (toc and data["gate"]) else toc
    sections_html = _render_sections(data["sections"])

    quiz_html = ""
    if data["quiz"]:
        quiz_qs = "\n".join(
            _render_question(q, "quiz", i) for i, q in enumerate(data["quiz"])
        )
        quiz_html = f'''  <section id="quiz-section" class="doc-section">
    <h2>Quiz</h2>
    <p class="muted">Confirm it stuck. Answer positions are shuffled.</p>
    <div class="card" id="quiz">
{quiz_qs}
    </div>
    <div class="row"><button id="quiz-check">Check answers</button></div>
    <div id="quiz-result" class="verdict" hidden></div>
  </section>'''

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(data["title"])}</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
  <header class="page">
    <h1>{e(data["title"])}</h1>
    {subtitle}
  </header>

  {gate_html}

{toc_hidden}

  <div id="deep-content"{deep_hidden}>
{sections_html}

{quiz_html}
  </div>
</div>
<script>{JS}</script>
</body>
</html>
'''


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main(argv=None):
    ap = argparse.ArgumentParser(description="Render an explain-diff JSON spec to HTML.")
    ap.add_argument("spec", help="Path to JSON spec, or '-' for stdin.")
    ap.add_argument("-o", "--output", help="Output HTML path (default: stdout).")
    args = ap.parse_args(argv)

    raw = sys.stdin.read() if args.spec == "-" else open(args.spec, encoding="utf-8").read()
    try:
        spec = json.loads(raw)
    except json.JSONDecodeError as ex:
        sys.exit(f"render.py: invalid JSON spec: {ex}")

    try:
        out = render(spec)
    except ValueError as ex:
        sys.exit(f"render.py: {ex}")

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(out)
        print(f"Wrote {args.output}")
    else:
        sys.stdout.write(out)


if __name__ == "__main__":
    main()
