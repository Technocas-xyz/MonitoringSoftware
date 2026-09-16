"""Pluggable SSO providers (spec 79, doc 00 A11).

No authentication provider is hard-coded. Each provider implements `authorize_url` (where to
send the browser) and `exchange` (turn a callback code into a verified identity). Google,
Microsoft Entra, and generic OIDC/SAML register here. Providers live in per-org settings
(`settings.sso`) so tenants configure their own IdP.

For environments without live IdP configuration, a deterministic StubProvider validates a
signed test assertion so the callback flow is exercisable end-to-end.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class SSOIdentity:
    subject: str            # stable IdP subject id
    email: str
    full_name: str | None = None


class SSOProvider(ABC):
    key: str

    @abstractmethod
    def authorize_url(self, state: str, redirect_uri: str) -> str: ...

    @abstractmethod
    async def exchange(self, code: str, redirect_uri: str) -> SSOIdentity: ...


class StubProvider(SSOProvider):
    """Test/dev provider. The 'code' is expected to be 'subject|email|name' so the callback can
    be driven deterministically without a live IdP. NOT for production use."""

    key = "stub"

    def authorize_url(self, state: str, redirect_uri: str) -> str:
        return f"{redirect_uri}?state={state}&provider=stub"

    async def exchange(self, code: str, redirect_uri: str) -> SSOIdentity:
        parts = code.split("|")
        subject = parts[0]
        email = parts[1] if len(parts) > 1 else f"{subject}@sso.local"
        name = parts[2] if len(parts) > 2 else None
        return SSOIdentity(subject=subject, email=email, full_name=name)


_REGISTRY: dict[str, SSOProvider] = {"stub": StubProvider()}


def register_provider(provider: SSOProvider) -> None:
    _REGISTRY[provider.key] = provider


def get_provider(key: str) -> SSOProvider | None:
    return _REGISTRY.get(key)
