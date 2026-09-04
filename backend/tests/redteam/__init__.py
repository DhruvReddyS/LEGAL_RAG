"""Adversarial tests for the tenant boundary.

Separate from the correctness suite on purpose. Those tests ask whether the
code does what it was told; these ask whether a caller can reach material that
belongs to someone else. A green correctness suite has already coexisted with a
live cross-tenant disclosure in this codebase.
"""
