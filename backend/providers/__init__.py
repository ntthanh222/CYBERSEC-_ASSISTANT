"""Outbound integrations.

Every external system the backend talks to sits behind an abstract provider so
that the calling service never depends on a vendor SDK, and so tests can inject
a controlled implementation instead of reaching the network.
"""
