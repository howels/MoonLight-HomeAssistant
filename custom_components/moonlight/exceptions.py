"""Errors raised while talking to a MoonLight device.

Each type is a case the user can act on. The message is the detail that goes into the log
and, for a refused command, into the Home Assistant error the user sees.
"""

from __future__ import annotations


class MoonLightError(Exception):
    """The device could not be used. Subclasses name which case it is."""


class MoonLightConnectionError(MoonLightError):
    """The host did not answer, or the socket dropped."""


class MoonLightResponseError(MoonLightError):
    """The host answered with something other than MoonLight's API."""


class MoonLightCommandError(MoonLightError):
    """The device refused one change. The message is the device's own reason when it sent one."""


class MoonLightExpertError(MoonLightError):
    """Expert mode is off, so a factory reset or a filesystem format was not sent."""
