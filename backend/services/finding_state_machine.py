"""Finding status state machine - a pure function, no DB/HTTP involved.

This is the single, authoritative source of truth for which Finding status
transitions exist and which project/global roles may perform them. It is
deliberately kept side-effect-free and framework-free so it can be
exhaustively unit tested on its own (see
``backend/tests/test_finding_state_machine.py``) and then reused unchanged by
``backend.services.finding.FindingService.transition``.

Role rules (see the Task 2 brief for the plan citations):

* ``open``/``confirmed``/``reopened`` -> the "triage tier" transitions
  (confirm, dismiss as false positive/accepted risk, move to in_progress,
  reopen back into the workflow) require project_role ``owner``/``security``,
  or a global ``admin``/``super_admin`` (unconditional bypass, matching
  ``require_project_role``'s semantics from Task 1).
* ``in_progress`` -> ``fixed``/``false_positive``/``accepted_risk``: the
  assignee (a ``developer`` project-role member who is also the finding's
  ``assignee_user_id``) may additionally perform these, on top of
  owner/security/admin.
* ``fixed`` -> ``verified`` and ``verified`` -> ``closed``: owner/security/
  admin ONLY. A developer project-role actor is **never** allowed here, even
  if they are the assignee - this is a hard, literal requirement from the
  plan ("Developers CANNOT self-transition to VERIFIED/CLOSED") and must
  never be softened or made configurable.
* Any transition INTO ``false_positive`` or ``accepted_risk`` (from any
  state) requires a non-empty ``reason``.
"""
from __future__ import annotations

from typing import Optional

#: Every reachable (from_status -> {to_status, ...}) edge in the state
#: machine, independent of who may traverse it - see ``_ROLE_GATED_STATUSES``
#: below for the authorization layer on top of this graph.
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "open": frozenset({"confirmed", "false_positive", "accepted_risk"}),
    "confirmed": frozenset({"in_progress", "false_positive", "accepted_risk"}),
    "in_progress": frozenset({"fixed", "false_positive", "accepted_risk"}),
    "fixed": frozenset({"verified", "reopened"}),
    "verified": frozenset({"closed", "reopened"}),
    "closed": frozenset({"reopened"}),
    "false_positive": frozenset({"reopened"}),
    "accepted_risk": frozenset({"reopened"}),
    "reopened": frozenset({"confirmed", "in_progress"}),
}

_GLOBAL_BYPASS_ROLES = ("admin", "super_admin")
_TRIAGE_ROLES = ("owner", "security")

#: Transitions only owner/security/admin may ever perform - a developer
#: project-role actor is refused here unconditionally, even as the
#: assignee. Kept as its own set (rather than "everything not in the
#: assignee-eligible set") so the hard "never" rule is a literal, readable
#: fact in code rather than something implied by exclusion.
_OWNER_SECURITY_ONLY_EDGES = frozenset(
    {
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
    }
)

#: Transitions the assignee (a developer project-role member who is also
#: the finding's assignee_user_id) may additionally perform, on top of
#: owner/security/admin.
_ASSIGNEE_ELIGIBLE_EDGES = frozenset(
    {
        ("in_progress", "fixed"),
        ("in_progress", "false_positive"),
        ("in_progress", "accepted_risk"),
    }
)

#: Target statuses that always require a non-empty reason, regardless of
#: the from_status.
_REASON_REQUIRED_TARGETS = frozenset({"false_positive", "accepted_risk"})


class FindingStateMachineError(Exception):
    """Base class for every state-machine validation failure."""


class InvalidTransitionError(FindingStateMachineError):
    """``to_status`` is not a reachable edge from ``from_status`` at all."""


class ForbiddenTransitionError(FindingStateMachineError):
    """The edge exists, but this actor's role may not traverse it."""


class ReasonRequiredError(FindingStateMachineError):
    """A false_positive/accepted_risk transition was attempted with no
    (or an empty/whitespace-only) reason."""


def validate_transition(
    from_status: str,
    to_status: str,
    actor_project_role: Optional[str],
    actor_global_role: Optional[str],
    is_assignee: bool,
    reason: Optional[str],
) -> None:
    """Raise if ``actor`` may not move a Finding from ``from_status`` to
    ``to_status``; return ``None`` (no exception) if the transition is
    allowed.

    ``actor_project_role`` is ``None`` when the actor has no direct
    ``ProjectMember`` row (e.g. authorized only via the workspace-owner/
    admin bypass) - such an actor is treated the same as an explicit
    owner/security role for every rule here, mirroring
    ``require_project_role``'s bypass semantics from Task 1: a caller who
    reached this far without a direct membership row got here via a bypass
    that already satisfies every role check.
    """
    edge = (from_status, to_status)
    reachable_targets = ALLOWED_TRANSITIONS.get(from_status, frozenset())
    if to_status not in reachable_targets:
        raise InvalidTransitionError(
            f"Cannot transition a finding from '{from_status}' to '{to_status}'."
        )

    if to_status in _REASON_REQUIRED_TARGETS and not (reason and reason.strip()):
        raise ReasonRequiredError(
            f"A non-empty reason is required to transition to '{to_status}'."
        )

    if actor_global_role in _GLOBAL_BYPASS_ROLES:
        return

    is_owner_or_security = actor_project_role in _TRIAGE_ROLES or actor_project_role is None
    if is_owner_or_security:
        return

    if edge in _ASSIGNEE_ELIGIBLE_EDGES and actor_project_role == "developer" and is_assignee:
        return

    raise ForbiddenTransitionError(
        "You do not have permission to perform this status transition."
    )
