"""Errors raised by aiozoneminder."""

from __future__ import annotations


class ZMError(Exception):
    """Base class for every aiozoneminder error."""


class ZMConnectionError(ZMError):
    """The ZoneMinder server could not be reached."""


class ZMAuthenticationError(ZMError):
    """Credentials were rejected, or the session could not be refreshed."""


class ZMApiError(ZMError):
    """The server was reached but returned an error."""


class ZMNotFoundError(ZMApiError):
    """The server answered 404: the thing asked for does not exist."""


class ZMNotSupportedError(ZMError):
    """The active backend does not implement the requested capability."""
