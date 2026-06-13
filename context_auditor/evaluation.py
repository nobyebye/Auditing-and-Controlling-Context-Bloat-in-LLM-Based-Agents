"""Lightweight task success evaluation for controlled experiments."""

from __future__ import annotations


def keyword_success(output: str, expected_keyword: str) -> bool:
    if not expected_keyword:
        return True
    return expected_keyword.lower() in output.lower()
