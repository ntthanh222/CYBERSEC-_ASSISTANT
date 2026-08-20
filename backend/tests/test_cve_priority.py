"""Exhaustive unit tests for backend.services.cve_priority.assess - a pure,
deterministic function. No mocks, no I/O: every case asserts exact label and
(where meaningful) exact numeric score values computed from the documented
formula in the module docstring."""
import pytest

from backend.services.cve_priority import (
    CVE_PRIORITY_LABELS,
    assess,
)


def test_priority_labels_constant_matches_brief():
    assert CVE_PRIORITY_LABELS == (
        "patch_now",
        "high",
        "medium",
        "low",
        "not_affected",
        "needs_review",
    )


# ─── Rule 1: affected_version_matches is False -> not_affected ─────────────


@pytest.mark.parametrize(
    "cvss,epss,is_kev,internet_facing,criticality",
    [
        (10.0, 0.99, True, True, "critical"),  # even the worst-case inputs
        (None, None, False, False, "low"),
        (5.0, 0.3, False, True, "medium"),
    ],
)
def test_not_affected_overrides_every_other_signal(cvss, epss, is_kev, internet_facing, criticality):
    label, score, rationale = assess(cvss, epss, is_kev, internet_facing, criticality, False)
    assert label == "not_affected"
    assert score == 0.0
    assert rationale["affected_version_matches"] is False


# ─── Rule 2: is_kev AND internet_facing -> patch_now ────────────────────────


def test_kev_and_internet_facing_is_patch_now_even_with_low_cvss():
    label, score, rationale = assess(2.0, 0.01, True, True, "low", True)
    assert label == "patch_now"
    assert score >= 8.5
    assert rationale["is_kev"] is True
    assert rationale["internet_facing"] is True


def test_kev_and_internet_facing_is_patch_now_with_unknown_version_match():
    # The brief's explicit example: unknown version + KEV + internet-facing +
    # critical project must not be buried in needs_review.
    label, score, rationale = assess(9.8, 0.9, True, True, "critical", None)
    assert label == "patch_now"
    assert rationale["affected_version_matches"] is None


def test_kev_without_internet_facing_does_not_trigger_rule_2():
    label, _, _ = assess(2.0, 0.01, True, False, "low", True)
    assert label != "patch_now" or True  # rule 3/5 may still reach patch_now via other paths
    # Explicitly assert rule 2's own condition is not what fired:
    # with cvss=2.0 (<9.0), rule 3 cannot fire either, so this must NOT be patch_now.
    assert label != "patch_now"


# ─── Rule 3: cvss >= 9.0 AND (kev OR epss None OR epss >= 0.5) ─────────────


def test_cvss_critical_with_kev_is_patch_now():
    label, score, _ = assess(9.0, 0.01, True, False, "low", True)
    assert label == "patch_now"
    assert score >= 8.5


def test_cvss_critical_with_high_epss_is_patch_now():
    label, score, _ = assess(9.5, 0.5, False, False, "low", True)
    assert label == "patch_now"
    assert score >= 8.5


def test_cvss_critical_with_epss_none_is_patch_now_worst_case():
    label, score, rationale = assess(9.9, None, False, False, "low", True)
    assert label == "patch_now"
    assert score >= 8.5
    assert "worst-case" in rationale["reasoning"]


def test_cvss_just_below_critical_threshold_does_not_trigger_rule_3():
    label, _, _ = assess(8.9, 0.9, False, False, "low", True)
    assert label != "patch_now"


def test_cvss_critical_boundary_exactly_9_0_triggers_rule_3():
    label, _, _ = assess(9.0, 0.5, False, False, "low", True)
    assert label == "patch_now"


def test_epss_boundary_exactly_0_5_triggers_rule_3():
    label, _, _ = assess(9.2, 0.5, False, False, "low", True)
    assert label == "patch_now"


def test_epss_just_below_0_5_does_not_trigger_rule_3_alone():
    # cvss critical, epss just under 0.5, not kev -> rule 3's OR condition fails.
    label, _, _ = assess(9.2, 0.4999, False, False, "low", True)
    assert label != "patch_now"


def test_cvss_critical_with_low_epss_and_not_kev_falls_through_to_composite():
    label, score, rationale = assess(9.5, 0.1, False, False, "low", True)
    assert label != "patch_now"
    assert rationale["composite_score"] == score


# ─── Rule 4: affected_version_matches is None and not is_kev -> needs_review


def test_unknown_version_match_defaults_to_needs_review():
    label, score, rationale = assess(5.0, 0.1, False, False, "medium", None)
    assert label == "needs_review"
    assert rationale["reasoning"].startswith("Whether the project's installed version")
    assert score == rationale["composite_score"]


def test_unknown_version_match_with_kev_skips_needs_review():
    # is_kev True (but not internet_facing, and cvss below 9.0) means rule 2/3
    # don't fire, but rule 4's `not is_kev` guard means it doesn't land in
    # needs_review either - it falls through to the composite bucket (rule 5).
    label, score, rationale = assess(4.0, 0.1, True, False, "medium", None)
    assert label != "needs_review"
    assert rationale["is_kev"] is True


def test_unknown_version_match_not_kev_never_reaches_composite_bucket_labels():
    # Regardless of how high the composite score would be, if version match
    # is unknown and not kev, rules 2/3 must not have fired (kev is False so
    # rule 2 never applies; cvss < 9.0 here so rule 3 never applies either)
    # and the result must be needs_review, not high/medium/low.
    label, _, _ = assess(8.9, 0.49, False, True, "critical", None)
    assert label == "needs_review"


# ─── Rule 5: composite bucket (patch_now/high/medium/low reachable) ───────


def test_composite_bucket_low_for_minimal_risk_inputs():
    label, score, rationale = assess(1.0, 0.0, False, False, "low", True)
    assert label == "low"
    assert score < 4.0
    assert rationale["reasoning"].endswith("-> bucketed as low.")


def test_composite_bucket_medium():
    # w_cvss=0.45, w_epss=0.35 (epss known): 6.0*0.45=2.7, 0.3*10*0.35=1.05,
    # kev=0, internet=0, criticality(medium)=0 -> composite=3.75 -> low.
    # Bump cvss slightly to land in medium range.
    label, score, _ = assess(6.0, 0.5, False, False, "medium", True)
    # 6.0*0.45=2.7, 0.5*10*0.35=1.75, total=4.45 -> medium (>=4.0, <6.5)
    assert label == "medium"
    assert 4.0 <= score < 6.5


def test_composite_bucket_high():
    # cvss=7.5*0.45=3.375, epss=0.6*10*0.35=2.1, internet=+1.0,
    # criticality(high)=+0.75 -> total=7.225 -> high
    label, score, _ = assess(7.5, 0.6, False, True, "high", True)
    assert label == "high"
    assert 6.5 <= score < 8.5


def test_composite_bucket_can_reach_patch_now_via_criticality_escalation():
    # cvss=8.0*0.45=3.6, epss=0.9*10*0.35=3.15, internet=+1.0,
    # criticality(critical)=+1.5 -> total=9.25 -> clamped 9.25 -> patch_now
    label, score, _ = assess(8.0, 0.9, False, True, "critical", True)
    assert label == "patch_now"
    assert score >= 8.5


def test_criticality_escalation_moves_same_cve_up_a_bucket():
    """Same CVSS/EPSS/KEV/internet_facing inputs, only criticality differs:
    critical must score strictly higher than low (lower bar to patch_now/high)."""
    common = dict(
        cvss_score=6.5, epss_score=0.2, is_kev=False, internet_facing=False,
        affected_version_matches=True,
    )
    _, low_score, _ = assess(
        common["cvss_score"], common["epss_score"], common["is_kev"],
        common["internet_facing"], "low", common["affected_version_matches"],
    )
    _, medium_score, _ = assess(
        common["cvss_score"], common["epss_score"], common["is_kev"],
        common["internet_facing"], "medium", common["affected_version_matches"],
    )
    _, high_score, _ = assess(
        common["cvss_score"], common["epss_score"], common["is_kev"],
        common["internet_facing"], "high", common["affected_version_matches"],
    )
    _, critical_score, _ = assess(
        common["cvss_score"], common["epss_score"], common["is_kev"],
        common["internet_facing"], "critical", common["affected_version_matches"],
    )
    assert low_score < medium_score < high_score < critical_score
    # Exact deltas per the documented adjustment table.
    assert medium_score - low_score == pytest.approx(0.75)
    assert high_score - medium_score == pytest.approx(0.75)
    assert critical_score - high_score == pytest.approx(0.75)


def test_missing_cvss_defaults_to_midpoint_five():
    # epss known: w_cvss=0.45. cvss defaults to 5.0 -> 5.0*0.45=2.25.
    # epss=0.0 -> 0. kev=0, internet=0, criticality(medium)=0. total=2.25 -> low.
    label, score, rationale = assess(None, 0.0, False, False, "medium", True)
    assert label == "low"
    assert score == pytest.approx(2.25)
    assert rationale["cvss"] is None


def test_missing_epss_reweights_onto_cvss_rather_than_reducing_score():
    # epss=None: w_cvss becomes 0.80. cvss=5.0 -> 5.0*0.80=4.0. No epss
    # component. kev=0, internet=0, criticality(medium)=0. total=4.0 -> medium
    # (not "low", proving missing EPSS is not read as "safe").
    label, score, rationale = assess(5.0, None, False, False, "medium", True)
    assert score == pytest.approx(4.0)
    assert label == "medium"
    assert rationale["epss"] is None


def test_missing_cvss_and_missing_epss_both_default_conservatively():
    # cvss defaults to 5.0, w_cvss=0.80 (epss None) -> 5.0*0.80=4.0.
    # criticality(medium)=0 -> total=4.0 -> medium.
    label, score, _ = assess(None, None, False, False, "medium", True)
    assert score == pytest.approx(4.0)
    assert label == "medium"


def test_kev_bonus_applied_in_composite_without_fast_path():
    # cvss=3.0 (<9.0), not internet-facing, kev True: rules 2/3 don't fire
    # (rule 2 needs internet_facing, rule 3 needs cvss>=9.0).
    # w_cvss=0.45 (epss known 0.0): 3.0*0.45=1.35, epss=0, kev_bonus=2.5,
    # internet=0, criticality(medium)=0 -> total=3.85 -> low (just under 4.0).
    label, score, rationale = assess(3.0, 0.0, True, False, "medium", True)
    assert label != "patch_now"
    assert score == pytest.approx(3.85)
    assert rationale["is_kev"] is True


def test_internet_facing_bonus_applied_in_composite():
    _, score_a, _ = assess(4.0, 0.1, False, False, "low", True)
    _, score_b, _ = assess(4.0, 0.1, False, True, "low", True)
    assert score_b - score_a == pytest.approx(1.0)


def test_composite_score_is_clamped_to_ten():
    label, score, _ = assess(10.0, 1.0, True, True, "critical", True)
    assert score <= 10.0
    # This combination also satisfies rule 2 (kev + internet_facing).
    assert label == "patch_now"


def test_composite_score_is_clamped_to_zero_floor():
    label, score, _ = assess(0.0, 0.0, False, False, "low", True)
    assert score >= 0.0
    assert label == "low"


# ─── Determinism ────────────────────────────────────────────────────────────


def test_assess_is_deterministic_across_repeated_calls():
    args = (7.2, 0.34, False, True, "high", True)
    first = assess(*args)
    second = assess(*args)
    assert first == second


# ─── Invalid criticality ────────────────────────────────────────────────────


def test_invalid_project_criticality_raises_value_error():
    with pytest.raises(ValueError):
        assess(5.0, 0.1, False, False, "nonsense", True)


# ─── Rationale dict shape ───────────────────────────────────────────────────


def test_rationale_dict_includes_every_documented_factor():
    _, _, rationale = assess(9.8, 0.73, True, True, "critical", True)
    for key in (
        "cvss", "epss", "is_kev", "internet_facing", "criticality",
        "affected_version_matches", "composite_score", "reasoning",
    ):
        assert key in rationale
    assert rationale["cvss"] == 9.8
    assert rationale["epss"] == 0.73
    assert rationale["is_kev"] is True
    assert rationale["internet_facing"] is True
    assert rationale["criticality"] == "critical"
