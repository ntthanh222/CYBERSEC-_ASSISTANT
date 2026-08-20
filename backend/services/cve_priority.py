"""Deterministic CVE risk-prioritization engine (Task 6).

This is a **pure function** - no network, no DB, no LLM calls anywhere in
this module. Same inputs always produce the same ``(label, score,
rationale)`` output. It is the core of "CVE Risk Prioritization": given a
CVE's CVSS score (from the existing NVD-backed ``CveLookupService``), its
EPSS exploit-probability score (from the new ``EpssProvider``), whether it is
CISA KEV-listed (from the new ``KevProvider``), and the project's own risk
context (criticality, internet-facing, and whether the installed version is
actually confirmed affected), it produces one of six priority labels plus a
0-10 numeric composite score and a plain-language rationale dict.

There is no external spec for "the correct" CVE prioritization formula this
task can cite - it is a made-up, documented business rule. The design intent
below is deliberately simple and auditable over "clever": every factor's
contribution is visible in the ``rationale`` dict returned alongside the
label, because a later (out-of-scope-for-this-task) AI-copilot phase is
expected to surface this rationale as an explanation, and the frontend
renders it directly.

## Rule table (evaluated top to bottom, first match wins)

1. ``affected_version_matches is False`` (explicitly confirmed the
   project's installed version is NOT in the vulnerable range):
   -> ``"not_affected"``, score ``0.0``, unconditionally. Nothing else
   matters once affectedness itself has been ruled out.

2. ``is_kev is True AND internet_facing is True``:
   -> ``"patch_now"``. Known-exploited-in-the-wild plus internet-facing is
   the textbook worst case (an attacker does not need privileged network
   access to reach the target, and exploitation is not theoretical) - this
   fires even when ``affected_version_matches`` is still ``None``
   (unknown), because this combination is dangerous enough that burying it
   in "needs_review" behind an unresolved version check would be worse than
   a false positive.

3. ``cvss_score >= 9.0`` (CVSS-critical) AND
   (``is_kev`` OR ``epss_score is None`` OR ``epss_score >= 0.5``):
   -> ``"patch_now"``. A CVSS-critical CVE where either it is confirmed
   actively exploited, or the exploit-probability model puts a 50%+ chance
   on exploitation within the next scoring period, or EPSS coverage itself
   is simply unavailable (treated as the worst case here, not the safe
   case - see the composite formula's own EPSS-missing handling below for
   why "unknown EPSS" is never read as "low risk").

4. ``affected_version_matches is None`` (unknown/not checked) AND
   ``is_kev is False``:
   -> ``"needs_review"``. An unresolved "is this version even affected?"
   question is itself the actionable signal here - a human should confirm
   affectedness before this CVE gets bucketed into an ordinary
   high/medium/low queue. The ``is_kev is False`` guard is what lets rule 2
   fire ahead of this one for *any* KEV-listed CVE (not just the
   KEV+internet-facing case already handled by rule 2): a confirmed
   actively-exploited CVE is judged unambiguous enough to skip the
   "needs_review" holding pen and go straight to the composite bucket below
   instead, per the brief's explicit example (a KEV CVE should not be
   buried in needs_review just because the version match is unresolved).

5. Otherwise: compute the weighted composite score below and bucket it.

## Composite score (0-10), used by rule 5 and to size the reported score
   for every other branch

    composite = cvss_component + epss_component
                + kev_bonus + internet_facing_bonus
                + criticality_adjustment

    clamped to [0, 10].

- **cvss_component** = ``(cvss_score if cvss_score is not None else 5.0)
  * w_cvss``. A missing CVSS score defaults to the scale's midpoint (5.0,
  "unknown severity" is treated as moderate, neither best- nor
  worst-case) rather than 0 (which would silently read as "harmless") or
  10 (which would drown out every other signal for CVEs the lookup
  service simply has no CVSS data for).
- **epss_component** = ``epss_score * 10 * w_epss`` when ``epss_score`` is
  known, else ``0`` - but see the reweighting below, this is not the same
  as "missing EPSS contributes nothing to the total".
- **w_cvss / w_epss**: normally ``0.45`` / ``0.35`` (CVSS and EPSS are the
  two dominant technical signals; CVSS is weighted slightly higher because
  it is always attempted first-party NVD data, EPSS coverage is
  best-effort). When ``epss_score is None``, EPSS's ``0.35`` share is
  folded entirely into CVSS (``w_cvss = 0.80``, ``w_epss = 0``) - this is
  the concrete implementation of "treat missing EPSS as unknown, weight
  the CVSS side more" from the brief: missing EPSS data never reduces the
  composite score (it would if the 0.35 share were just dropped), it
  makes the CVSS signal count for more instead.
- **kev_bonus** = ``+2.5`` if ``is_kev`` else ``0`` - confirmed active
  exploitation is a strong standalone escalator even outside the rule-2/3
  fast paths (e.g. KEV-listed but not internet-facing).
- **internet_facing_bonus** = ``+1.0`` if ``internet_facing`` else ``0`` -
  reachability is a first-order risk multiplier independent of the CVE's
  own severity.
- **criticality_adjustment**: ``critical -> +1.5``, ``high -> +0.75``,
  ``medium -> 0.0``, ``low -> -0.75``. This is what gives a
  ``critical``-criticality project a systematically lower bar to
  ``"patch_now"``/``"high"`` than a ``low``-criticality one for identical
  CVSS/EPSS/KEV inputs, per the brief's explicit requirement - the same
  CVE lands 2.25 points higher on a critical-criticality project than on a
  low-criticality one.

## Bucket thresholds (applied to the composite score)

    score >= 8.5  -> "patch_now"
    score >= 6.5  -> "high"
    score >= 4.0  -> "medium"
    else          -> "low"

("not_affected" and "needs_review" are never reached via thresholds - they
are the two terminal branches above, rules 1 and 4.)

## Reported numeric score per branch

- Rule 1 (``not_affected``): always ``0.0``, overriding the composite
  formula entirely - affectedness has been ruled out, so the composite's
  CVSS/EPSS/criticality inputs are no longer relevant to *this* project.
- Rules 2/3 (``patch_now`` via the fast paths): ``max(composite, 8.5)``
  (clamped to 10) - the fast-path label is authoritative, so the reported
  score is pulled up to be consistent with the "patch_now" bucket's own
  floor even if the underlying composite formula alone would have landed
  lower (e.g. a KEV+internet-facing CVE with low CVSS/EPSS still needs a
  score that reads as urgent, not moderate).
- Rule 4 (``needs_review``): the plain composite score, unmodified - shown
  for transparency (a reviewer can see roughly how urgent the CVE looks
  once affectedness is confirmed) but the *label* is what drives action,
  not this number.
- Rule 5: the plain composite score, unmodified.
"""
from typing import Any, Optional

CVE_PRIORITY_LABELS = (
    "patch_now",
    "high",
    "medium",
    "low",
    "not_affected",
    "needs_review",
)

_PROJECT_CRITICALITIES = ("low", "medium", "high", "critical")

_W_CVSS = 0.45
_W_CVSS_NO_EPSS = 0.80
_W_EPSS = 0.35
_CVSS_UNKNOWN_DEFAULT = 5.0

_KEV_BONUS = 2.5
_INTERNET_FACING_BONUS = 1.0
_CRITICALITY_ADJUSTMENTS = {
    "critical": 1.5,
    "high": 0.75,
    "medium": 0.0,
    "low": -0.75,
}

_THRESHOLD_PATCH_NOW = 8.5
_THRESHOLD_HIGH = 6.5
_THRESHOLD_MEDIUM = 4.0


def _clamp(value: float, *, low: float = 0.0, high: float = 10.0) -> float:
    return max(low, min(high, value))


def _composite_score(
    *,
    cvss_score: Optional[float],
    epss_score: Optional[float],
    is_kev: bool,
    internet_facing: bool,
    project_criticality: str,
) -> float:
    if epss_score is None:
        w_cvss, w_epss = _W_CVSS_NO_EPSS, 0.0
    else:
        w_cvss, w_epss = _W_CVSS, _W_EPSS

    cvss_value = cvss_score if cvss_score is not None else _CVSS_UNKNOWN_DEFAULT
    cvss_component = cvss_value * w_cvss
    epss_component = (epss_score * 10 * w_epss) if epss_score is not None else 0.0
    kev_bonus = _KEV_BONUS if is_kev else 0.0
    internet_bonus = _INTERNET_FACING_BONUS if internet_facing else 0.0
    criticality_adj = _CRITICALITY_ADJUSTMENTS[project_criticality]

    total = cvss_component + epss_component + kev_bonus + internet_bonus + criticality_adj
    return _clamp(total)


def _bucket(score: float) -> str:
    if score >= _THRESHOLD_PATCH_NOW:
        return "patch_now"
    if score >= _THRESHOLD_HIGH:
        return "high"
    if score >= _THRESHOLD_MEDIUM:
        return "medium"
    return "low"


def assess(
    cvss_score: Optional[float],
    epss_score: Optional[float],
    is_kev: bool,
    internet_facing: bool,
    project_criticality: str,
    affected_version_matches: Optional[bool],
) -> tuple[str, float, dict[str, Any]]:
    """Compute ``(priority_label, numeric_score, rationale_dict)``.

    Pure, deterministic, synchronous - no I/O of any kind. See the module
    docstring for the full rule table and composite-score formula.
    """
    if project_criticality not in _PROJECT_CRITICALITIES:
        raise ValueError(
            f"project_criticality must be one of {_PROJECT_CRITICALITIES}, "
            f"got {project_criticality!r}."
        )

    composite = _composite_score(
        cvss_score=cvss_score,
        epss_score=epss_score,
        is_kev=is_kev,
        internet_facing=internet_facing,
        project_criticality=project_criticality,
    )

    base_rationale: dict[str, Any] = {
        "cvss": cvss_score,
        "epss": epss_score,
        "is_kev": is_kev,
        "internet_facing": internet_facing,
        "criticality": project_criticality,
        "affected_version_matches": affected_version_matches,
        "composite_score": round(composite, 4),
    }

    # Rule 1: confirmed not affected overrides everything else.
    if affected_version_matches is False:
        rationale = {
            **base_rationale,
            "reasoning": (
                "The project's installed version was explicitly confirmed to be "
                "outside the vulnerable range, so this CVE does not apply here "
                "regardless of its CVSS/EPSS/KEV status."
            ),
        }
        return "not_affected", 0.0, rationale

    # Rule 2: known-exploited + internet-facing is the textbook worst case.
    if is_kev and internet_facing:
        score = _clamp(max(composite, _THRESHOLD_PATCH_NOW))
        rationale = {
            **base_rationale,
            "reasoning": (
                "CISA KEV-listed (confirmed actively exploited in the wild) AND the "
                "project is internet-facing - an attacker needs no privileged "
                "network access and exploitation is not theoretical. Escalated to "
                "patch_now regardless of the affected-version check."
            ),
        }
        return "patch_now", score, rationale

    # Rule 3: CVSS-critical with a strong exploitation signal (or unknown
    # EPSS, treated as the worst case rather than the safe case).
    if cvss_score is not None and cvss_score >= 9.0 and (
        is_kev or epss_score is None or epss_score >= 0.5
    ):
        score = _clamp(max(composite, _THRESHOLD_PATCH_NOW))
        if is_kev:
            epss_reason = "it is also KEV-listed"
        elif epss_score is None:
            epss_reason = "EPSS coverage is unavailable, treated as worst-case here"
        else:
            epss_reason = f"EPSS ({epss_score:.2f}) indicates a >=50% exploitation probability"
        rationale = {
            **base_rationale,
            "reasoning": (
                f"CVSS {cvss_score:.1f} is critical (>=9.0) and {epss_reason} - "
                "escalated to patch_now."
            ),
        }
        return "patch_now", score, rationale

    # Rule 4: unresolved affectedness is itself the actionable signal,
    # unless the CVE is already confirmed actively exploited (is_kev),
    # which is judged unambiguous enough to skip straight to the
    # composite bucket instead of the needs_review holding pen.
    if affected_version_matches is None and not is_kev:
        rationale = {
            **base_rationale,
            "reasoning": (
                "Whether the project's installed version is actually in the "
                "vulnerable range was not checked/could not be determined. This is "
                "flagged for human review rather than auto-bucketed by CVSS/EPSS "
                "alone."
            ),
        }
        return "needs_review", composite, rationale

    # Rule 5: weighted composite bucket.
    label = _bucket(composite)
    rationale = {
        **base_rationale,
        "reasoning": (
            f"Composite score {composite:.2f}/10 from CVSS "
            f"({cvss_score if cvss_score is not None else 'unknown, defaulted to 5.0'}), "
            f"EPSS ({epss_score if epss_score is not None else 'unknown, weight shifted to CVSS'}), "
            f"KEV={is_kev}, internet_facing={internet_facing}, "
            f"criticality={project_criticality} -> bucketed as {label}."
        ),
    }
    return label, composite, rationale
