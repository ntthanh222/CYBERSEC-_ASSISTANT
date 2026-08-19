"""Exhaustive pure-function tests for backend.services.finding_state_machine.

No DB, no HTTP - every (from_status, to_status, actor role/assignee/reason)
combination that should succeed or fail is covered here, especially the two
hard requirements from the Task 2 brief:

1. A developer project-role actor can NEVER transition fixed->verified or
   verified->closed, even if they are the finding's assignee.
2. Any transition into false_positive/accepted_risk requires a non-empty
   reason, regardless of from_status or actor role.
"""
import itertools

import pytest

from backend.services.finding_state_machine import (
    ALLOWED_TRANSITIONS,
    ForbiddenTransitionError,
    InvalidTransitionError,
    ReasonRequiredError,
    validate_transition,
)

ALL_STATUSES = (
    "open",
    "confirmed",
    "in_progress",
    "fixed",
    "verified",
    "closed",
    "false_positive",
    "accepted_risk",
    "reopened",
)

ALL_PROJECT_ROLES = ("owner", "security", "developer", "viewer", None)

_REASON_REQUIRED_TARGETS = {"false_positive", "accepted_risk"}


def _reason_for(to_status: str) -> str | None:
    return "Because reasons." if to_status in _REASON_REQUIRED_TARGETS else None


# ─── Every non-edge is invalid, regardless of role ─────────────────────────


@pytest.mark.parametrize(
    "from_status,to_status",
    [
        (f, t)
        for f, t in itertools.product(ALL_STATUSES, ALL_STATUSES)
        if t not in ALLOWED_TRANSITIONS.get(f, frozenset())
    ],
)
def test_non_edges_always_raise_invalid_transition(from_status, to_status):
    with pytest.raises(InvalidTransitionError):
        validate_transition(
            from_status,
            to_status,
            actor_project_role="owner",
            actor_global_role=None,
            is_assignee=False,
            reason=_reason_for(to_status),
        )


def test_invalid_transition_wins_over_missing_reason():
    # open -> verified is not a real edge at all; even though 'verified'
    # doesn't require a reason, this must still be InvalidTransitionError,
    # not silently treated as some other failure.
    with pytest.raises(InvalidTransitionError):
        validate_transition(
            "open", "verified", actor_project_role="owner", actor_global_role=None,
            is_assignee=False, reason=None,
        )


# ─── Global admin/super_admin bypass: always allowed on any real edge ──────


@pytest.mark.parametrize("global_role", ["admin", "super_admin"])
@pytest.mark.parametrize(
    "from_status,to_status",
    [(f, t) for f, targets in ALLOWED_TRANSITIONS.items() for t in targets],
)
def test_global_admin_bypass_allows_every_edge(from_status, to_status, global_role):
    validate_transition(
        from_status,
        to_status,
        actor_project_role="developer",  # even the most restricted role
        actor_global_role=global_role,
        is_assignee=False,
        reason=_reason_for(to_status),
    )  # must not raise


def test_global_admin_bypass_still_requires_a_reason_for_false_positive():
    with pytest.raises(ReasonRequiredError):
        validate_transition(
            "open", "false_positive", actor_project_role="developer",
            actor_global_role="admin", is_assignee=False, reason=None,
        )


# ─── Owner/security tier transitions ───────────────────────────────────────


_OWNER_SECURITY_EDGES = [
    ("open", "confirmed"),
    ("open", "false_positive"),
    ("open", "accepted_risk"),
    ("confirmed", "in_progress"),
    ("confirmed", "false_positive"),
    ("confirmed", "accepted_risk"),
    ("fixed", "verified"),
    ("verified", "closed"),
    ("reopened", "confirmed"),
    ("reopened", "in_progress"),
    ("closed", "reopened"),
    ("false_positive", "reopened"),
    ("accepted_risk", "reopened"),
]


@pytest.mark.parametrize("role", ["owner", "security"])
@pytest.mark.parametrize("from_status,to_status", _OWNER_SECURITY_EDGES)
def test_owner_and_security_may_perform_triage_tier_edges(role, from_status, to_status):
    validate_transition(
        from_status, to_status, actor_project_role=role, actor_global_role=None,
        is_assignee=False, reason=_reason_for(to_status),
    )  # must not raise


@pytest.mark.parametrize("role", ["developer", "viewer"])
@pytest.mark.parametrize("from_status,to_status", _OWNER_SECURITY_EDGES)
def test_developer_and_viewer_are_forbidden_from_triage_tier_edges(role, from_status, to_status):
    with pytest.raises(ForbiddenTransitionError):
        validate_transition(
            from_status, to_status, actor_project_role=role, actor_global_role=None,
            is_assignee=True,  # even as assignee - irrelevant for these edges
            reason=_reason_for(to_status),
        )


def test_bypass_actor_with_no_project_role_is_treated_as_owner_equivalent():
    """actor_project_role=None models a caller authorized only via the
    workspace-owner/admin bypass (Task 1's get_project_member semantics) -
    such a caller has no direct ProjectMember row but is still fully
    authorized, same as an explicit owner/security role."""
    validate_transition(
        "open", "confirmed", actor_project_role=None, actor_global_role=None,
        is_assignee=False, reason=None,
    )  # must not raise


# ─── in_progress -> {fixed, false_positive, accepted_risk}: assignee tier ──


_ASSIGNEE_EDGES = [
    ("in_progress", "fixed"),
    ("in_progress", "false_positive"),
    ("in_progress", "accepted_risk"),
]


@pytest.mark.parametrize("from_status,to_status", _ASSIGNEE_EDGES)
def test_developer_assignee_may_perform_in_progress_edges(from_status, to_status):
    validate_transition(
        from_status, to_status, actor_project_role="developer", actor_global_role=None,
        is_assignee=True, reason=_reason_for(to_status),
    )  # must not raise


@pytest.mark.parametrize("from_status,to_status", _ASSIGNEE_EDGES)
def test_developer_non_assignee_is_forbidden_from_in_progress_edges(from_status, to_status):
    with pytest.raises(ForbiddenTransitionError):
        validate_transition(
            from_status, to_status, actor_project_role="developer", actor_global_role=None,
            is_assignee=False, reason=_reason_for(to_status),
        )


@pytest.mark.parametrize("from_status,to_status", _ASSIGNEE_EDGES)
def test_viewer_assignee_is_still_forbidden_from_in_progress_edges(from_status, to_status):
    # is_assignee alone never grants access - the role must also be developer
    # (or owner/security/admin, covered elsewhere).
    with pytest.raises(ForbiddenTransitionError):
        validate_transition(
            from_status, to_status, actor_project_role="viewer", actor_global_role=None,
            is_assignee=True, reason=_reason_for(to_status),
        )


@pytest.mark.parametrize("from_status,to_status", _ASSIGNEE_EDGES)
def test_owner_and_security_may_also_perform_in_progress_edges(from_status, to_status):
    for role in ("owner", "security"):
        validate_transition(
            from_status, to_status, actor_project_role=role, actor_global_role=None,
            is_assignee=False, reason=_reason_for(to_status),
        )  # must not raise


# ─── Hard requirement: developers can NEVER verify/close, even as assignee ─


@pytest.mark.parametrize("from_status,to_status", [("fixed", "verified"), ("verified", "closed")])
@pytest.mark.parametrize("is_assignee", [True, False])
def test_developer_can_never_verify_or_close_even_as_assignee(from_status, to_status, is_assignee):
    with pytest.raises(ForbiddenTransitionError):
        validate_transition(
            from_status, to_status, actor_project_role="developer", actor_global_role=None,
            is_assignee=is_assignee, reason=None,
        )


@pytest.mark.parametrize("from_status,to_status", [("fixed", "verified"), ("verified", "closed")])
def test_viewer_cannot_verify_or_close(from_status, to_status):
    with pytest.raises(ForbiddenTransitionError):
        validate_transition(
            from_status, to_status, actor_project_role="viewer", actor_global_role=None,
            is_assignee=False, reason=None,
        )


# ─── reopened -> {confirmed, in_progress}: same tier as open/confirmed ─────


@pytest.mark.parametrize("to_status", ["confirmed", "in_progress"])
@pytest.mark.parametrize("role", ["owner", "security"])
def test_owner_and_security_may_reopen_forward(to_status, role):
    validate_transition(
        "reopened", to_status, actor_project_role=role, actor_global_role=None,
        is_assignee=False, reason=None,
    )  # must not raise


@pytest.mark.parametrize("to_status", ["confirmed", "in_progress"])
@pytest.mark.parametrize("role", ["developer", "viewer"])
def test_developer_and_viewer_cannot_reopen_forward(to_status, role):
    with pytest.raises(ForbiddenTransitionError):
        validate_transition(
            "reopened", to_status, actor_project_role=role, actor_global_role=None,
            is_assignee=True, reason=None,
        )


# ─── ->reopened from closed/false_positive/accepted_risk: owner/security only


@pytest.mark.parametrize("from_status", ["closed", "false_positive", "accepted_risk"])
@pytest.mark.parametrize("role", ["owner", "security"])
def test_owner_and_security_may_reopen_a_resolved_finding(from_status, role):
    validate_transition(
        from_status, "reopened", actor_project_role=role, actor_global_role=None,
        is_assignee=False, reason=None,
    )  # must not raise


@pytest.mark.parametrize("from_status", ["closed", "false_positive", "accepted_risk"])
@pytest.mark.parametrize("role", ["developer", "viewer"])
def test_developer_and_viewer_cannot_reopen_a_resolved_finding(from_status, role):
    with pytest.raises(ForbiddenTransitionError):
        validate_transition(
            from_status, "reopened", actor_project_role=role, actor_global_role=None,
            is_assignee=True, reason=None,
        )


# ─── Reason required for ->false_positive / ->accepted_risk from any state ─


@pytest.mark.parametrize(
    "from_status,to_status",
    [(f, t) for f, targets in ALLOWED_TRANSITIONS.items() for t in targets if t in _REASON_REQUIRED_TARGETS],
)
@pytest.mark.parametrize("bad_reason", [None, "", "   "])
def test_reason_required_for_false_positive_and_accepted_risk(from_status, to_status, bad_reason):
    with pytest.raises(ReasonRequiredError):
        validate_transition(
            from_status, to_status, actor_project_role="owner", actor_global_role=None,
            is_assignee=False, reason=bad_reason,
        )


@pytest.mark.parametrize(
    "from_status,to_status",
    [(f, t) for f, targets in ALLOWED_TRANSITIONS.items() for t in targets if t in _REASON_REQUIRED_TARGETS],
)
def test_non_empty_reason_is_accepted(from_status, to_status):
    validate_transition(
        from_status, to_status, actor_project_role="owner", actor_global_role=None,
        is_assignee=False, reason="Confirmed as a false positive after manual review.",
    )  # must not raise


def test_reason_not_required_for_transitions_outside_the_resolution_targets():
    # e.g. open -> confirmed never requires a reason.
    validate_transition(
        "open", "confirmed", actor_project_role="owner", actor_global_role=None,
        is_assignee=False, reason=None,
    )  # must not raise


def test_reason_check_happens_before_role_check_for_a_valid_edge():
    # A forbidden actor on a reason-required edge with no reason should still
    # surface as ReasonRequiredError per the module's documented check order
    # (edge validity, then reason, then role).
    with pytest.raises(ReasonRequiredError):
        validate_transition(
            "open", "false_positive", actor_project_role="developer", actor_global_role=None,
            is_assignee=False, reason=None,
        )


# ─── Every declared edge is exercised by at least one success-path test ────


def test_every_declared_edge_has_at_least_one_authorized_actor_combination():
    """Sanity check: no edge in ALLOWED_TRANSITIONS is unreachable by every
    possible actor - would indicate a typo'd role rule."""
    for from_status, targets in ALLOWED_TRANSITIONS.items():
        for to_status in targets:
            reason = _reason_for(to_status)
            # owner should always be able to reach it in this state machine.
            validate_transition(
                from_status, to_status, actor_project_role="owner", actor_global_role=None,
                is_assignee=False, reason=reason,
            )
