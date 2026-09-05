"""Render a calibration result as markdown.

Two structural rules, both there to stop a reader drawing more from the
numbers than the numbers support:

  * The limits section comes before the figures. Someone who reads the top of
    this document and stops must already know what it cannot tell them.
  * No interval is printed without its sample size. An interval whose n is a
    footnote invites a reader to treat a 12-item result like a 1200-item one.
"""

VERDICT_TEXT = {
    "at_or_above_ceiling": (
        "The judge reaches the ceiling. Its agreement with humans is at least "
        "as good as humans manage with each other, which is the most any "
        "instrument can do on this task."
    ),
    "below_ceiling": (
        "The judge falls below the ceiling. Humans agree with each other more "
        "than the judge agrees with them, so automating this rubric costs "
        "measurable accuracy."
    ),
    "no_ceiling": (
        "No verdict is possible, because there is no ceiling to compare "
        "against."
    ),
}


def _number(value, places=3):
    return "—" if value is None else format(value, ".%df" % places)


def _interval(block):
    """An interval always travels with the n it was computed from."""
    if block is None or block["alpha"] is None:
        return "—"
    if block["ci"] is None:
        return "%s (no interval, n = %d)" % (_number(block["alpha"]), block["n"])
    low, high = block["ci"]
    return "%s, 95%% CI [%s, %s], n = %d" % (
        _number(block["alpha"]),
        _number(low),
        _number(high),
        block["n"],
    )


def render(data, agreement_result, bias_result, clusters, power_result,
           title=None):
    """Assemble the markdown calibration report."""
    lines = ["# %s" % (title or "Judge calibration report"), ""]

    lines += [
        "Judge column `%s` against %d human rater column(s), %d items."
        % (data.judge_column, data.human_rater_count, data.n),
        "",
        "## What this report cannot tell you",
        "",
    ]
    limits = list(data.notes) + list(agreement_result["notes"])
    if agreement_result["verdict"] == "no_ceiling":
        limits.append(
            "**Gate 6 is unanswered.** Whether the judge is good enough to "
            "automate cannot be decided from this data."
        )
    limits.append(
        "This report measures agreement, not correctness. A judge that agrees "
        "with a mistaken human is still wrong."
    )
    lines += ["- %s" % note for note in limits]
    lines.append("")

    lines += ["## Agreement", ""]
    lines.append(
        "Judge-human agreement (Krippendorff's alpha): %s"
        % _interval(agreement_result["judge_human"])
    )
    lines.append("")
    if agreement_result["human_human"] is not None:
        lines.append(
            "Human-human agreement, the ceiling: %s"
            % _interval(agreement_result["human_human"])
        )
        lines.append("")
    lines += [VERDICT_TEXT[agreement_result["verdict"]], ""]

    lines += ["## Statistical power", ""]
    if power_result["baseline"] is None:
        lines.append("Not computable: no comparable rows.")
    else:
        lines.append(
            "Observed exact-agreement rate: %s over %d items."
            % (_number(power_result["baseline"]), power_result["n"])
        )
        if power_result["mde"] is not None:
            lines.append(
                "Smallest difference this many items can detect: %s."
                % _number(power_result["mde"])
            )
        else:
            lines.append(
                "This item count cannot detect any difference at conventional "
                "alpha and power. Any comparison drawn from it is noise."
            )
        if power_result["mid"] is not None:
            lines.append(
                "To detect a difference of %s you would need %d items; you "
                "have %d, which is %s."
                % (
                    _number(power_result["mid"]),
                    power_result["n_required"],
                    power_result["n"],
                    "enough" if power_result["sufficient"] else "not enough",
                )
            )
    lines.append("")

    lines += ["## Judge bias", ""]
    if bias_result["length"] is not None:
        gap = bias_result["length"]["gap"]
        lines.append(
            "Length: judge rho %s against human rho %s, gap %s."
            % (
                _number(bias_result["length"]["judge_rho"]),
                _number(bias_result["length"]["human_rho"]),
                _number(gap),
            )
        )
        lines.append(
            "The gap is the finding, not the judge's own correlation — longer "
            "answers are sometimes genuinely better."
        )
        lines.append("")
    if bias_result["self_preference"] is not None:
        lines.append(
            "Self-preference: own outputs %s against others %s, delta %s."
            % (
                _number(bias_result["self_preference"]["own_mean"]),
                _number(bias_result["self_preference"]["other_mean"]),
                _number(bias_result["self_preference"]["delta"]),
            )
        )
        lines.append("")
    if bias_result["unavailable"]:
        lines += ["**Not measured:**", ""]
        lines += ["- %s" % item for item in bias_result["unavailable"]]
        lines.append("")

    lines += ["## Disagreement clusters", ""]
    if not clusters:
        lines.append("The judge and the human never disagreed.")
    else:
        lines += [
            "Biggest first. These are counts, not causes — name each pattern "
            "yourself by reading the items behind it.",
            "",
            "| Human | Judge | Count | Share | Example items |",
            "|---|---|---|---|---|",
        ]
        for cluster in clusters:
            examples = ", ".join(str(i) for i in cluster["item_ids"][:5]) or "—"
            lines.append(
                "| %s | %s | %d | %s | %s |"
                % (
                    cluster["human"],
                    cluster["judge"],
                    cluster["count"],
                    _number(cluster["share"], 2),
                    examples,
                )
            )
    lines.append("")

    return "\n".join(lines)
