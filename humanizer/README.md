# humanizer (vendored)

A vendored copy of the [humanizer](https://github.com/blader/humanizer) skill by
[blader](https://github.com/blader) (MIT, © 2025 Siqi Chen), pinned at **v2.9.1**.
It removes signs of AI-generated writing from text. See
[`skills/humanizer/SKILL.md`](skills/humanizer/SKILL.md) for the full guide: 33
patterns (em-dash overuse, rule-of-three padding, promotional language, "AI
vocabulary", filler, hedging, and more) based on Wikipedia's "Signs of AI
writing".

## Use it on its own

Install from this marketplace and run it on any text:

```
/plugin install humanizer@explain-code-marketplace
```

Then ask it to "Humanize this text: ..." or point it at a file ("Humanize the
prose in docs/launch-post.md"). The skill supports three invocation modes:
pasted text, file (rewrites in place), and embedded (called by another skill).

## Use it with improvement-plan

The `improvement-plan` skill's language step (Step 6) calls this skill in
*embedded mode* as a final pass, so a drafted plan gets the same plain-language
scrub before it goes out. Humanizer handles AI-tell removal; improvement-plan
keeps its own rules (counts in parentheses, defined jargon, forecast ranges)
that humanizer does not cover. The two are complementary, not redundant.

## Updating

This is a copy, not a git submodule. To update, re-pull `skills/humanizer/SKILL.md`
and `LICENSE` from the upstream repo, then bump the version in
`.claude-plugin/plugin.json` and the pin noted above. Do not hand-edit the
patterns here; send fixes upstream so this copy stays a faithful mirror.

## License

MIT — see [LICENSE](LICENSE). Upstream: https://github.com/blader/humanizer
