#!/usr/bin/env python3
"""
check_ste.py — flag Simplified Technical English (ASD-STE100) violations in prose.

Why this exists
---------------
Most of what makes prose hard for a non-native or hurried reader is mechanical:
sentences that run past the word cap, passive constructions that hide the actor,
stacked participles, four-noun pile-ups, phrasal verbs, idioms, and the same
concept named three different ways. A model rewriting text can fix all of those
and still miss one, because it is reading for meaning, not counting. This script
counts.

What it deliberately does NOT do
--------------------------------
  * It does not check the ASD-STE100 approved-word dictionary. That dictionary is
    ASD copyright and is not redistributable, so it is not bundled here (see
    ../references/rules.md). Dictionary conformance needs the real specification.
  * It does not judge whether the rewrite preserved the technical meaning. Only a
    reader can do that. A clean run is a floor, not a pass.
  * It does not rewrite anything. Every finding hands the fix back to the author.

Code is never checked. Fenced blocks, indented blocks, <pre>/<code> elements, and
inline backtick spans are blanked out before any rule runs, so an identifier like
`isRunningBackfill` is not a participle violation and a `git push --force` line is
not an imperative-mood finding.

Usage
-----
    python3 check_ste.py draft.md                    # lite profile (default)
    python3 check_ste.py draft.md --profile strict
    cat draft.md | python3 check_ste.py -            # read stdin
    python3 check_ste.py draft.md --format json      # machine-readable

Exit status is 1 when any error-level finding remains, 0 otherwise (warnings do
not fail the run). Pure Python 3 standard library.
"""

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
VOCAB_PATH = os.path.join(HERE, "..", "references", "engineering-vocabulary.md")

# Word caps per profile: (descriptive, procedural). A "procedural" sentence is one
# written as an instruction — see _is_procedural.
CAPS = {
    "lite": (25, 20),
    "strict": (20, 20),
}

MAX_PARAGRAPH_SENTENCES = 6

# Words that end a noun run: articles, prepositions, conjunctions, pronouns and
# common verbs. Four content words with none of these between them is the
# noun-cluster tell (rules.md, chapter 2).
FUNCTION_WORDS = {
    "a", "an", "the", "this", "that", "these", "those", "its", "their", "his",
    "her", "our", "your", "my", "and", "or", "but", "nor", "so", "yet", "if",
    "when", "while", "because", "although", "though", "unless", "until", "than",
    "as", "of", "for", "to", "in", "on", "at", "by", "with", "from", "into",
    "onto", "over", "under", "after", "before", "between", "through", "during",
    "without", "within", "about", "against", "per", "via", "is", "are", "was",
    "were", "be", "been", "being", "has", "have", "had", "do", "does", "did",
    "will", "would", "can", "could", "may", "might", "must", "should", "shall",
    "it", "he", "she", "they", "we", "you", "i", "not", "no", "all", "any",
    "each", "every", "some", "both", "either", "neither", "which", "who", "whom",
    "whose", "what", "there", "here", "then", "now", "also", "only", "just",
    # Particles and quantifiers. Without these, a phrasal verb plus its object
    # ("spin up more workers") reads as a four-noun pile-up and reports a cluster
    # that isn't one.
    "up", "down", "out", "off", "back", "away", "again", "more", "less", "most",
    "least", "many", "much", "few", "several", "other", "another", "same", "such",
    "new", "own", "next", "last", "first", "one", "two", "three",
}

BE_FORMS = {"is", "are", "was", "were", "be", "been", "being", "get", "gets", "got"}

# `-ed` words that are adjectives after `be`, not passives. "the payload is
# malformed" describes a state and has no hidden actor to name, so flagging it
# just trains the author to ignore the passive rule.
ADJECTIVAL_ED = {
    "malformed", "deprecated", "distributed", "advanced", "detailed", "limited",
    "related", "complicated", "dedicated", "isolated", "unexpected", "required",
    "outdated", "unsupported", "undefined", "unused", "unchanged", "disabled",
    "enabled", "empty", "closed", "corrupted", "expired", "authenticated",
    "authorised", "authorized", "encrypted", "compressed", "nested", "shared",
    "supported", "documented", "intended", "interested", "concerned", "aware",
}

# Irregular past participles that don't end in -ed, for the passive-voice check.
IRREGULAR_PARTICIPLES = {
    "given", "taken", "written", "read", "sent", "built", "kept", "held", "made",
    "run", "done", "seen", "shown", "known", "found", "lost", "left", "set",
    "put", "cut", "split", "shut", "spent", "meant", "dealt", "felt", "told",
    "sold", "brought", "bought", "caught", "taught", "thought", "fought",
    "chosen", "driven", "drawn", "thrown", "grown", "blown", "broken", "spoken",
    "frozen", "stolen", "forgotten", "hidden", "bitten", "beaten", "eaten",
    "fallen", "risen", "proven", "overwritten", "rewritten", "rebuilt", "resent",
}

# -ing words that are ordinary nouns or adjectives in technical prose, not verbs.
# Chains of these are not participle chains.
BENIGN_ING = {
    "string", "thing", "something", "nothing", "anything", "everything",
    "during", "morning", "warning", "setting", "settings", "meaning", "logging",
    "testing", "training", "engineering", "monitoring", "tooling", "onboarding",
    "encoding", "padding", "ranking", "sampling", "caching", "batching",
    "polling", "routing", "queueing", "queuing", "hashing", "backing",
    "following", "missing", "existing", "remaining", "leading", "trailing",
    "outstanding", "pending", "incoming", "outgoing", "underlying", "corresponding",
}

IMPERATIVE_STARTERS = {
    "add", "apply", "build", "call", "change", "check", "click", "close",
    "configure", "connect", "copy", "create", "delete", "deploy", "disable",
    "do", "download", "edit", "enable", "enter", "install", "keep", "list",
    "load", "make", "merge", "move", "note", "open", "pull", "push", "read",
    "release", "remove", "rename", "replace", "restart", "restore", "revert",
    "run", "save", "select", "send", "set", "start", "stop", "store", "try",
    "update", "upload", "use", "verify", "wait", "write",
}


# --------------------------------------------------------------------------- #
# Finding
# --------------------------------------------------------------------------- #

class Finding:
    def __init__(self, line, rule, level, message, excerpt=""):
        self.line = line
        self.rule = rule
        self.level = level
        self.message = message
        self.excerpt = excerpt

    def as_dict(self):
        return {
            "line": self.line, "rule": self.rule, "level": self.level,
            "message": self.message, "excerpt": self.excerpt,
        }

    def __str__(self):
        # Line 0 means the finding is about the document as a whole (terminology
        # drift spans every use), so don't point at a line that isn't the culprit.
        where = f"line {self.line}" if self.line else "document"
        head = f"{where}: {self.level}: [{self.rule}] {self.message}"
        return f"{head}\n    {self.excerpt}" if self.excerpt else head


# --------------------------------------------------------------------------- #
# Vocabulary table (parsed from ../references/engineering-vocabulary.md)
# --------------------------------------------------------------------------- #

def load_vocabulary(path=VOCAB_PATH):
    """Parse substitution tables and synonym groups out of the reference file.

    The reference doc is the single source of truth so the prose a human reads and
    the list the checker enforces cannot drift apart. Sections are delimited by
    `<!-- checker:substitutions -->` and `<!-- checker:synonyms -->` markers; a
    marker applies until the next marker or the next `---` rule.

    Returns (substitutions, synonym_groups). Missing or unreadable file yields
    empty collections — the structural rules still run.
    """
    subs, groups = [], []
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return subs, groups

    mode = None
    for raw in lines:
        line = raw.strip()
        if line.startswith("<!-- checker:substitutions"):
            mode = "subs"
            continue
        if line.startswith("<!-- checker:synonyms"):
            mode = "syn"
            continue
        if line.startswith("---") and set(line) == {"-"}:
            mode = None
            continue
        if mode == "subs" and line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) != 3:
                continue
            avoid, better, level = cells
            if avoid.lower() == "avoid" or set(avoid) <= {"-", ":"}:
                continue  # header or separator row
            if level not in ("error", "warn"):
                continue
            subs.append((avoid.lower(), better, level))
        elif mode == "syn" and line.startswith("- "):
            terms = [t.strip().lower() for t in line[2:].split(",") if t.strip()]
            if len(terms) > 1:
                groups.append(terms)

    # First definition of a term wins, so a duplicate row can't silently shadow.
    seen, deduped = set(), []
    for avoid, better, level in subs:
        if avoid in seen:
            continue
        seen.add(avoid)
        deduped.append((avoid, better, level))
    return deduped, groups


# --------------------------------------------------------------------------- #
# Masking: blank out everything that isn't prose
# --------------------------------------------------------------------------- #

def mask_non_prose(text):
    """Replace code and markup with spaces, preserving line numbers and offsets.

    Blanking rather than deleting keeps every remaining character at its original
    line and column, so findings point at the right place in the user's file.
    """
    def blank(match):
        return re.sub(r"[^\n]", " ", match.group(0))

    # Order matters: fenced blocks first, so a stray backtick inside one can't
    # start an inline span that swallows the rest of the document.
    text = re.sub(r"^[ \t]*(```|~~~).*?^[ \t]*\1[^\n]*$", blank,
                  text, flags=re.S | re.M)
    text = re.sub(r"<(pre|code|script|style)\b.*?</\1>", blank,
                  text, flags=re.S | re.I)
    text = re.sub(r"`[^`\n]+`", blank, text)
    # Indented code blocks: 4+ spaces, but not a continuation of a list item.
    text = re.sub(r"^(?: {4,}|\t)(?![-*+] ).*$", blank, text, flags=re.M)
    # Markdown link targets and bare URLs are not prose to be rewritten.
    text = re.sub(r"\]\([^)\s]+\)", blank, text)
    text = re.sub(r"https?://\S+", blank, text)
    # Remaining HTML tags (keep the text between them).
    text = re.sub(r"<[^>\n]{1,200}>", blank, text)
    return text


# --------------------------------------------------------------------------- #
# Segmentation
# --------------------------------------------------------------------------- #

ABBREVIATIONS = {"e.g", "i.e", "etc", "vs", "cf", "approx", "no", "fig", "sec"}

_SENT_END = re.compile(r"([.!?])[\"')\]]*(\s+|$)")


def split_sentences(block):
    """Split a text block into (sentence, offset) pairs. Deliberately simple."""
    out, start = [], 0
    for m in _SENT_END.finditer(block):
        end = m.end(1)
        candidate = block[start:end]
        word = re.search(r"([A-Za-z.]+)\s*$", candidate[:-1] or "")
        tail = (word.group(1).lower().rstrip(".") if word else "")
        if tail in ABBREVIATIONS:
            continue  # "e.g." is not a sentence boundary
        if candidate.strip():
            out.append((candidate.strip(), start))
        start = m.end()
    rest = block[start:]
    if rest.strip():
        out.append((rest.strip(), start))
    return out


def split_blocks(text):
    """Split masked text into paragraph-ish blocks of (text, start_offset)."""
    blocks, buf, buf_start = [], [], None
    offset = 0
    for line in text.split("\n"):
        stripped = line.strip()
        is_break = not stripped or stripped.startswith("#") or stripped.startswith("|")
        if is_break:
            if buf:
                blocks.append(("\n".join(buf), buf_start))
                buf, buf_start = [], None
            # A heading is its own block: heading text still obeys the rules.
            if stripped.startswith("#"):
                blocks.append((stripped.lstrip("#").strip(), offset))
        else:
            if buf_start is None:
                buf_start = offset
            buf.append(line)
        offset += len(line) + 1
    if buf:
        blocks.append(("\n".join(buf), buf_start))
    return blocks


def line_of(text, offset):
    return text.count("\n", 0, offset) + 1


def words_of(sentence):
    """Content words, lowercased, with list markers and punctuation stripped."""
    cleaned = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", sentence)
    return re.findall(r"[A-Za-z][A-Za-z'’\-]*", cleaned.lower())


# --------------------------------------------------------------------------- #
# Rules
# --------------------------------------------------------------------------- #

def _is_procedural(words):
    """True when the sentence reads as an instruction rather than a description."""
    return bool(words) and words[0] in IMPERATIVE_STARTERS


def check_sentence_length(sentence, words, profile):
    desc_cap, proc_cap = CAPS[profile]
    cap = proc_cap if _is_procedural(words) else desc_cap
    kind = "procedural" if _is_procedural(words) else "descriptive"
    n = len(words)
    if n > cap:
        return Finding(
            0, "sentence-length", "error",
            f"{n}-word {kind} sentence (cap is {cap}). Split it at a conjunction; "
            "do not compress by deleting articles.",
            _excerpt(sentence),
        )
    return None


def check_passive(sentence, words, profile):
    """Flag `be` + past participle. Heuristic, so it is a warning in lite."""
    for i, w in enumerate(words[:-1]):
        if w not in BE_FORMS:
            continue
        nxt = words[i + 1]
        # Allow one adverb between the auxiliary and the participle.
        if nxt.endswith("ly") and i + 2 < len(words):
            nxt = words[i + 2]
        if nxt in ADJECTIVAL_ED:
            continue
        is_participle = (
            nxt in IRREGULAR_PARTICIPLES
            or (nxt.endswith("ed") and len(nxt) > 4 and nxt not in ("need", "feed", "speed"))
        )
        if is_participle:
            level = "error" if profile == "strict" else "warn"
            return Finding(
                0, "passive-voice", level,
                f"passive construction ('{w} {nxt}') hides who acts. Name the actor "
                "and use the active voice.",
                _excerpt(sentence),
            )
    return None


def check_participle_chain(sentence, words, profile):
    ing = [w for w in words if w.endswith("ing") and len(w) > 5 and w not in BENIGN_ING]
    # strict bans the -ing form outright; lite only flags a chain of them, which is
    # where the "what acts on what" ambiguity actually bites (rules.md, chapter 3).
    limit = 1 if profile == "strict" else 2
    if len(ing) >= limit:
        return Finding(
            0, "participle-chain", "error" if profile == "strict" else "warn",
            f"{len(ing)} '-ing' form(s) in one sentence ({', '.join(ing[:4])}). "
            "Rewrite as finite clauses so it is clear what acts on what.",
            _excerpt(sentence),
        )
    return None


def check_noun_cluster(sentence, words, profile):
    run = []
    for w in words:
        # A run is broken by function words, adverbs, and past-tense/participle
        # verbs. Without a POS tagger this is the closest cheap approximation to
        # "consecutive nouns", and it errs toward missing a cluster rather than
        # inventing one, because this rule reports at error level.
        if w in FUNCTION_WORDS or w.endswith("ly") or (w.endswith("ed") and len(w) > 4):
            run = []
            continue
        run.append(w)
        if len(run) >= 4:
            return Finding(
                0, "noun-cluster", "error",
                f"{len(run)}-word noun cluster ('{' '.join(run)}'). Lead with the head "
                "noun and reconnect the rest with 'of', 'for', or 'that'.",
                _excerpt(sentence),
            )
    return None


def check_substitutions(sentence, words, substitutions):
    found = []
    low = sentence.lower()
    for avoid, better, level in substitutions:
        pattern = r"\b" + re.escape(avoid).replace(r"\ ", r"\s+") + r"\b"
        if re.search(pattern, low):
            found.append(Finding(
                0, "word-choice", level,
                f"'{avoid}' -> '{better}'.",
                _excerpt(sentence),
            ))
    return found


def check_conditional_order(sentence, words):
    """The condition belongs before the instruction (rules.md, chapter 4)."""
    m = re.search(r",?\s+\b(if|when|unless)\b", sentence, re.I)
    if m and m.start() > 0 and _is_procedural(words):
        before = len(words_of(sentence[:m.start()]))
        if before >= 3:
            return Finding(
                0, "condition-order", "warn",
                "the condition comes after the instruction. Put 'if ...' first so the "
                "reader knows whether the sentence applies before reading what to do.",
                _excerpt(sentence),
            )
    return None


def check_terminology(all_words, groups):
    findings = []
    for group in groups:
        used = sorted({t for t in group if t in all_words})
        if len(used) > 1:
            findings.append(Finding(
                0, "terminology-drift", "warn",
                f"the document uses {', '.join(repr(u) for u in used)} for what is "
                "probably one concept. Pick one and use it everywhere.",
            ))
    return findings


def _excerpt(sentence, width=100):
    flat = " ".join(sentence.split())
    return flat if len(flat) <= width else flat[: width - 1] + "…"


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #

def check(text, profile="lite", substitutions=None, synonyms=None):
    """Run every rule over `text`. Returns a list of Findings, ordered by line."""
    if profile not in CAPS:
        raise ValueError(f"unknown profile {profile!r} (choose 'lite' or 'strict')")
    substitutions = substitutions if substitutions is not None else []
    synonyms = synonyms if synonyms is not None else []

    masked = mask_non_prose(text)
    findings = []
    vocabulary_words = set()

    for block, block_start in split_blocks(masked):
        sentences = split_sentences(block)
        for sentence, rel in sentences:
            words = words_of(sentence)
            if not words:
                continue
            vocabulary_words.update(words)
            line = line_of(masked, block_start + rel)

            per_sentence = [
                check_sentence_length(sentence, words, profile),
                check_passive(sentence, words, profile),
                check_participle_chain(sentence, words, profile),
                check_noun_cluster(sentence, words, profile),
                check_conditional_order(sentence, words),
            ]
            per_sentence += check_substitutions(sentence, words, substitutions)
            for f in per_sentence:
                if f is None:
                    continue
                f.line = line
                findings.append(f)

        if len(sentences) > MAX_PARAGRAPH_SENTENCES:
            f = Finding(
                line_of(masked, block_start), "paragraph-length", "warn",
                f"{len(sentences)}-sentence paragraph (cap is {MAX_PARAGRAPH_SENTENCES}). "
                "Split it, one topic each.",
            )
            findings.append(f)

    for f in check_terminology(vocabulary_words, synonyms):
        f.line = 0
        findings.append(f)

    findings.sort(key=lambda f: (f.line, f.rule))
    return findings


def report(findings, profile, stream=None):
    # Resolved at call time, not bound as a default: binding sys.stdout at import
    # would make the report ignore any later redirection of the stream.
    stream = sys.stdout if stream is None else stream
    errors = [f for f in findings if f.level == "error"]
    warnings = [f for f in findings if f.level == "warn"]
    for f in findings:
        stream.write(str(f) + "\n")
    if findings:
        stream.write("\n")
    stream.write(
        f"check_ste.py ({profile}): {len(errors)} error(s), {len(warnings)} warning(s).\n"
    )
    if not errors:
        stream.write(
            "No blocking findings. This is a floor, not a pass — reread the text to "
            "confirm the meaning survived.\n"
        )
    return 1 if errors else 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Flag Simplified Technical English (ASD-STE100) violations in prose.",
    )
    ap.add_argument("path", help="File to check, or '-' for stdin.")
    ap.add_argument("--profile", choices=sorted(CAPS), default="lite",
                    help="lite (default) keeps the rules that survive technical prose; "
                         "strict applies the full word caps and bans passive voice.")
    ap.add_argument("--format", choices=("text", "json"), default="text")
    ap.add_argument("--vocabulary", default=VOCAB_PATH,
                    help="Path to the substitution/synonym reference markdown.")
    args = ap.parse_args(argv)

    text = sys.stdin.read() if args.path == "-" else open(args.path, encoding="utf-8").read()
    substitutions, synonyms = load_vocabulary(args.vocabulary)
    findings = check(text, args.profile, substitutions, synonyms)

    if args.format == "json":
        json.dump({
            "profile": args.profile,
            "findings": [f.as_dict() for f in findings],
            "errors": sum(1 for f in findings if f.level == "error"),
            "warnings": sum(1 for f in findings if f.level == "warn"),
        }, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 1 if any(f.level == "error" for f in findings) else 0

    return report(findings, args.profile)


if __name__ == "__main__":
    sys.exit(main())
