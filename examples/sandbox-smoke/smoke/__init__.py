"""Trivial module the smoke tests exercise."""

from __future__ import annotations


def greet(name: str) -> str:
    if not name:
        raise ValueError("name is required")
    return f"สวัสดี {name}"


def add(a: int, b: int) -> int:
    return a + b
