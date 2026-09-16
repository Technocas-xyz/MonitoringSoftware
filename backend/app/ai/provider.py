"""Pluggable AI provider (doc 00 A10, spec 47).

The AI layer is optional and provider-agnostic. The default TemplateProvider composes
summaries/answers deterministically from already-gathered, RBAC-scoped metrics WITHOUT any
external call — so the platform works out of the box and tests are deterministic. An external
LLM provider can be plugged in by implementing AIProvider; it must be given only the
pre-authorized data (it never queries the database itself), preserving the RBAC guarantee.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class AIProvider(ABC):
    @abstractmethod
    def summarize(self, facts: dict) -> str: ...

    @abstractmethod
    def explain_anomaly(self, facts: dict) -> str: ...

    @abstractmethod
    def answer(self, question: str, facts: dict) -> str: ...


def _fmt_hms(seconds: int | None) -> str:
    s = int(seconds or 0)
    return f"{s // 3600}h {(s % 3600) // 60:02d}m"


class TemplateProvider(AIProvider):
    """Deterministic, no-network provider. Turns structured facts into readable prose."""

    def summarize(self, facts: dict) -> str:
        subject = facts.get("subject", "The employee")
        worked = _fmt_hms(facts.get("worked_seconds"))
        indicator = facts.get("indicator")
        top = facts.get("top_applications", [])
        idle = _fmt_hms(facts.get("idle_seconds"))
        parts = [f"{subject} worked {worked}."]
        if top:
            names = ", ".join(a["name"] for a in top[:3])
            parts.append(f"Most tracked activity was in {names}.")
        if facts.get("idle_seconds"):
            parts.append(f"Idle time totaled {idle}.")
        if indicator is not None:
            parts.append(f"Productivity indicator: {indicator}%.")
        return " ".join(parts)

    def explain_anomaly(self, facts: dict) -> str:
        if not facts.get("anomalous"):
            return "No unusual activity pattern detected relative to the typical baseline."
        changes = facts.get("changes", [])
        detail = "; ".join(
            f"{c['name']} {c['direction']} to {c['today_pct']}% (baseline {c['baseline_pct']}%)"
            for c in changes[:3]
        )
        return f"Unusual activity pattern detected. {detail}."

    def answer(self, question: str, facts: dict) -> str:
        # facts already contains the resolved answer computed within RBAC scope.
        answer = facts.get("answer")
        if answer is None:
            return "I can only answer questions about data you are authorized to view, and I could not resolve this one."
        return str(answer)


_provider: AIProvider = TemplateProvider()


def get_provider() -> AIProvider:
    return _provider


def set_provider(provider: AIProvider) -> None:
    global _provider
    _provider = provider
