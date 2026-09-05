"""Render a calibration result as markdown.

Two structural rules, both there to stop a reader drawing more from the
numbers than the numbers support:

  * The limits section comes before the figures. Someone who reads the top of
    this document and stops must already know what it cannot tell them.
  * No figure is printed without its sample size, and that size is the count
    the figure was computed from - pairable units for an alpha, complete rows
    for a correlation, comparable rows for the power baseline - never the
    file's row count. A figure whose n is a footnote invites a reader to treat
    a 12-item result like a 1200-item one; a figure carrying the wrong n does
    the same while looking careful.
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
}

# "no_ceiling" covers three different states, and one sentence cannot describe
# all three: the report printed a ceiling figure and then said, on the very
# next line, that there was no ceiling to compare against. The distinction is
# drawn here rather than in agreement_section, whose return contract is pinned
# by a test on purpose.
NO_VERDICT_TEXT = {
    "no_second_rater": (
        "No verdict is possible: with one human rater column there is no "
        "ceiling to compare the judge against."
    ),
    "ceiling_undefined": (
        "No verdict is possible: a second rater is present, but the "
        "human-human ceiling is itself undefined, so there is still nothing "
        "to measure the judge against."
    ),
    "judge_undefined": (
        "No verdict is possible: the ceiling above is defined, but the "
        "judge's own agreement figure is not, so the two cannot be compared."
    ),
}


def _verdict(agreement_result):
    """The sentence for this verdict, read together with the ceiling's state."""
    verdict = agreement_result["verdict"]
    if verdict in VERDICT_TEXT:
        return VERDICT_TEXT[verdict]
    if agreement_result["human_human"] is None:
        return NO_VERDICT_TEXT["no_second_rater"]
    if not agreement_result["ceiling_available"]:
        return NO_VERDICT_TEXT["ceiling_undefined"]
    return NO_VERDICT_TEXT["judge_undefined"]


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
    if agreement_result["verdict"] not in VERDICT_TEXT:
        limits.append(
            "**Gate 6 is unanswered.** Whether the judge is good enough to "
            "automate cannot be decided from this data."
        )
    if data.human_rater_count > 1:
        limits.append(
            "Only the agreement figures use every human rater column. The "
            "length-bias probe, the disagreement clusters and the power "
            "baseline all read `%s` alone, the first human rater column."
            % next(iter(data.human_columns))
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
    lines += [_verdict(agreement_result), ""]

    lines += ["## Statistical power", ""]
    if power_result["baseline"] is None:
        lines.append(
            "Not computable: no row carries both a judge score and a human "
            "label."
        )
    else:
        lines.append(
            "Observed exact-agreement rate: %s, n = %d rows carrying both a "
            "judge score and a human label."
            % (_number(power_result["baseline"]), power_result["n"])
        )
        if power_result["mde"] is not None:
            # mde_two_proportion returns the smallest detectable *proportion*,
            # so the difference is that proportion less the baseline. Printing
            # the proportion under a "difference" label put 0.999 beside a
            # 0.750 baseline, which is arithmetically impossible.
            lines.append(
                "Smallest difference this many items can detect: %s, which is "
                "an agreement rate of %s against the %s baseline, n = %d."
                % (
                    _number(power_result["mde"] - power_result["baseline"]),
                    _number(power_result["mde"]),
                    _number(power_result["baseline"]),
                    power_result["n"],
                )
            )
        else:
            lines.append(
                "This item count cannot detect any difference at conventional "
                "alpha and power. Any comparison drawn from it is noise."
            )
        if power_result["mid"] is not None:
            lines.append(
                "To detect a difference of %s you would need %d items per "
                "group; you have n = %d, which is %s."
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
            "Length: judge rho %s against human rho %s, gap %s, n = %d rows "
            "carrying a judge score, a human label and a length."
            % (
                _number(bias_result["length"]["judge_rho"]),
                _number(bias_result["length"]["human_rho"]),
                _number(gap),
                bias_result["length"]["n"],
            )
        )
        lines.append(
            "The gap is the finding, not the judge's own correlation — longer "
            "answers are sometimes genuinely better."
        )
        lines.append("")
    if bias_result["self_preference"] is not None:
        lines.append(
            "Self-preference: own outputs %s against others %s, delta %s, "
            "n = %d own and %d other."
            % (
                _number(bias_result["self_preference"]["own_mean"]),
                _number(bias_result["self_preference"]["other_mean"]),
                _number(bias_result["self_preference"]["delta"]),
                bias_result["self_preference"]["n_own"],
                bias_result["self_preference"]["n_other"],
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
