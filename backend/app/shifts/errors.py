"""Domain errors for shift transitions, mapped to HTTP status by the router."""
from __future__ import annotations


class ShiftError(Exception):
    status_code = 400
    code = "shift.error"

    def __init__(self, detail: str | None = None):
        super().__init__(detail or self.code)
        self.detail = detail or self.code


class InvalidTransition(ShiftError):
    status_code = 409
    code = "shift.invalid_transition"


class AlreadyActive(ShiftError):
    status_code = 409
    code = "shift.already_active"


class WindowNotOpen(ShiftError):
    status_code = 422
    code = "shift.window_not_open"


class NotPermitted(ShiftError):
    status_code = 403
    code = "shift.not_permitted"


class Conflict(ShiftError):
    status_code = 409
    code = "shift.conflict"


class NotFound(ShiftError):
    status_code = 404
    code = "shift.not_found"
