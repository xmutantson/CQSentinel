"""
N3FJP integration module.

Provides integration with N3FJP logging software for:
- Dupe checking
- Callsign information lookup
- Multiplier detection
- Log management

N3FJP is a popular Windows logging software for amateur radio contests.
"""

from .client import N3FJPClient, CallInfo, N3FJPStatus
from .multipliers import MultiplierTracker, ContestType

__all__ = [
    'N3FJPClient',
    'CallInfo',
    'N3FJPStatus',
    'MultiplierTracker',
    'ContestType',
]
