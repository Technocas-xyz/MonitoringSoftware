"""Notifications: template rendering + channel dispatch (spec 36/49/66).

Templates use {{placeholder}} substitution. Dispatch is abstracted per channel: in_app writes
a Notification row; email/push are pluggable providers (no-op logging by default). The alert
engine and other domains call dispatch() to reach recipients.
"""
from __future__ import annotations

import re
import uuid
from abc import ABC, abstractmethod

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.alerts import Notification, NotificationTemplate

log = get_logger("notifications")
_PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def render_template(body: str, context: dict) -> str:
    """Replace {{key}} with context[key]; unknown placeholders become empty strings."""
    def repl(m: re.Match) -> str:
        key = m.group(1)
        val = context.get(key)
        return "" if val is None else str(val)

    return _PLACEHOLDER.sub(repl, body)


class ChannelProvider(ABC):
    @abstractmethod
    async def send(self, session: AsyncSession, org_id: uuid.UUID, recipient_user_id: uuid.UUID | None,
                   title: str | None, body: str) -> None: ...


class InAppProvider(ChannelProvider):
    async def send(self, session, org_id, recipient_user_id, title, body):
        session.add(Notification(
            id=uuid.uuid4(), organization_id=org_id, recipient_user_id=recipient_user_id,
            channel="in_app", title=title, body=body,
        ))
        await session.flush()


class LoggingProvider(ChannelProvider):
    """Fallback provider for email/push until real providers are configured."""

    def __init__(self, channel: str):
        self.channel = channel

    async def send(self, session, org_id, recipient_user_id, title, body):
        log.info("notification.dispatch", channel=self.channel, org=str(org_id),
                 recipient=str(recipient_user_id), title=title)


def _provider_for(channel: str) -> ChannelProvider:
    if channel == "in_app":
        return InAppProvider()
    return LoggingProvider(channel)


async def _template(session: AsyncSession, org_id: uuid.UUID, key: str, channel: str) -> NotificationTemplate | None:
    return (
        await session.execute(
            select(NotificationTemplate).where(
                NotificationTemplate.organization_id == org_id,
                NotificationTemplate.key == key,
                NotificationTemplate.channel == channel,
            )
        )
    ).scalar_one_or_none()


async def dispatch(
    session: AsyncSession, org_id: uuid.UUID, *,
    template_key: str, channels: list[str], recipient_user_id: uuid.UUID | None,
    context: dict, fallback_body: str,
) -> None:
    """Render + send a notification over each channel. Falls back to a plain body if no
    template exists for the (key, channel)."""
    for channel in channels or ["in_app"]:
        tmpl = await _template(session, org_id, template_key, channel)
        if tmpl is not None:
            title = render_template(tmpl.subject or "", context) or None
            body = render_template(tmpl.body, context)
        else:
            title, body = None, fallback_body
        await _provider_for(channel).send(session, org_id, recipient_user_id, title, body)
