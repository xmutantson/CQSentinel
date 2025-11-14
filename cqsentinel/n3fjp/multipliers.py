"""
Multiplier detection logic for various contests.

Determines if a callsign/entity is a new multiplier based on:
- Contest type (Field Day, CQWW, etc.)
- Already worked multipliers
- Callsign prefix/suffix analysis
- Geographic data (state, DXCC, zone)
"""

import logging
import re
from typing import Set, Optional, List
from enum import Enum

from cqsentinel.n3fjp.client import CallInfo

logger = logging.getLogger(__name__)


class ContestType(Enum):
    """Contest types with different multiplier rules."""
    FIELD_DAY = "field_day"
    WINTER_FIELD_DAY = "winter_field_day"
    CQWW = "cqww"
    CQWPX = "cqwpx"
    SALMON_RUN = "salmon_run"
    GENERIC = "generic"


# ARRL/RAC sections for Field Day
ARRL_SECTIONS = {
    # US States
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    # Canadian Provinces
    "AB", "BC", "MB", "NB", "NL", "NS", "NT", "ON", "PE", "QC",
    "SK", "YT",
    # DX
    "DX"
}


# Washington State counties for Salmon Run
WA_COUNTIES = {
    "ADAMS", "ASOTIN", "BENTON", "CHELAN", "CLALLAM", "CLARK",
    "COLUMBIA", "COWLITZ", "DOUGLAS", "FERRY", "FRANKLIN",
    "GARFIELD", "GRANT", "GRAYS HARBOR", "ISLAND", "JEFFERSON",
    "KING", "KITSAP", "KITTITAS", "KLICKITAT", "LEWIS", "LINCOLN",
    "MASON", "OKANOGAN", "PACIFIC", "PEND OREILLE", "PIERCE",
    "SAN JUAN", "SKAGIT", "SKAMANIA", "SNOHOMISH", "SPOKANE",
    "STEVENS", "THURSTON", "WAHKIAKUM", "WALLA WALLA", "WHATCOM",
    "WHITMAN", "YAKIMA"
}


class MultiplierTracker:
    """
    Tracks worked multipliers for contest.

    Maintains sets of worked multipliers by type (section, DXCC, zone, etc.)
    and determines if a new callsign provides a new multiplier.

    Usage:
        tracker = MultiplierTracker(contest_type=ContestType.FIELD_DAY)

        # Mark multipliers as worked
        tracker.mark_worked_section("CT")
        tracker.mark_worked_section("MA")

        # Check if new multiplier
        if tracker.is_new_section("NY"):
            print("New section multiplier: NY")
    """

    def __init__(self, contest_type: ContestType = ContestType.GENERIC):
        """
        Initialize multiplier tracker.

        Args:
            contest_type: Type of contest
        """
        self.contest_type = contest_type

        # Worked multiplier sets
        self.worked_sections: Set[str] = set()
        self.worked_dxcc: Set[str] = set()
        self.worked_cq_zones: Set[str] = set()
        self.worked_prefixes: Set[str] = set()
        self.worked_counties: Set[str] = set()

        logger.info(f"MultiplierTracker initialized (contest: {contest_type.value})")

    def is_new_multiplier(
        self,
        callsign: str,
        call_info: Optional[CallInfo] = None
    ) -> bool:
        """
        Check if callsign provides a new multiplier.

        Args:
            callsign: Callsign to check
            call_info: CallInfo from N3FJP (optional)

        Returns:
            True if new multiplier

        Example:
            >>> tracker.is_new_multiplier("W1AW", call_info)
            True  # First CT station
        """
        if self.contest_type == ContestType.FIELD_DAY:
            return self._check_field_day_mult(callsign, call_info)
        elif self.contest_type == ContestType.WINTER_FIELD_DAY:
            return self._check_field_day_mult(callsign, call_info)  # Same rules
        elif self.contest_type == ContestType.CQWW:
            return self._check_cqww_mult(callsign, call_info)
        elif self.contest_type == ContestType.CQWPX:
            return self._check_cqwpx_mult(callsign, call_info)
        elif self.contest_type == ContestType.SALMON_RUN:
            return self._check_salmon_run_mult(callsign, call_info)
        else:
            # Generic: any new DXCC is mult
            if call_info and call_info.dxcc_name:
                return self.is_new_dxcc(call_info.dxcc_name)
            return False

    def is_new_section(self, section: str) -> bool:
        """Check if section is new multiplier."""
        section_upper = section.upper()
        return section_upper in ARRL_SECTIONS and section_upper not in self.worked_sections

    def is_new_dxcc(self, dxcc: str) -> bool:
        """Check if DXCC entity is new multiplier."""
        return dxcc not in self.worked_dxcc

    def is_new_cq_zone(self, zone: str) -> bool:
        """Check if CQ zone is new multiplier."""
        return zone not in self.worked_cq_zones

    def is_new_prefix(self, callsign: str) -> bool:
        """Check if callsign prefix is new multiplier."""
        prefix = self._extract_prefix(callsign)
        return prefix and prefix not in self.worked_prefixes

    def is_new_county(self, county: str) -> bool:
        """Check if county is new multiplier (Salmon Run)."""
        county_upper = county.upper()
        return county_upper in WA_COUNTIES and county_upper not in self.worked_counties

    def mark_worked_section(self, section: str):
        """Mark section as worked."""
        self.worked_sections.add(section.upper())

    def mark_worked_dxcc(self, dxcc: str):
        """Mark DXCC entity as worked."""
        self.worked_dxcc.add(dxcc)

    def mark_worked_cq_zone(self, zone: str):
        """Mark CQ zone as worked."""
        self.worked_cq_zones.add(zone)

    def mark_worked_prefix(self, callsign: str):
        """Mark callsign prefix as worked."""
        prefix = self._extract_prefix(callsign)
        if prefix:
            self.worked_prefixes.add(prefix)

    def mark_worked_county(self, county: str):
        """Mark county as worked."""
        self.worked_counties.add(county.upper())

    def mark_worked(
        self,
        callsign: str,
        call_info: Optional[CallInfo] = None
    ):
        """
        Mark all applicable multipliers as worked.

        Args:
            callsign: Callsign worked
            call_info: CallInfo from N3FJP
        """
        if call_info:
            if call_info.state and call_info.state in ARRL_SECTIONS:
                self.mark_worked_section(call_info.state)

            if call_info.dxcc_name:
                self.mark_worked_dxcc(call_info.dxcc_name)

            if call_info.cq_zone:
                self.mark_worked_cq_zone(call_info.cq_zone)

            if call_info.county:
                self.mark_worked_county(call_info.county)

        # Always mark prefix
        self.mark_worked_prefix(callsign)

    def _check_field_day_mult(
        self,
        callsign: str,
        call_info: Optional[CallInfo]
    ) -> bool:
        """Check Field Day multiplier (ARRL/RAC sections)."""
        if not call_info:
            return False

        # Field Day: ARRL/RAC sections
        if call_info.state:
            return self.is_new_section(call_info.state)

        return False

    def _check_cqww_mult(
        self,
        callsign: str,
        call_info: Optional[CallInfo]
    ) -> bool:
        """Check CQWW multiplier (DXCC + CQ zones)."""
        if not call_info:
            return False

        # CQWW: Both DXCC and CQ zones are multipliers
        is_new_dxcc = False
        is_new_zone = False

        if call_info.dxcc_name:
            is_new_dxcc = self.is_new_dxcc(call_info.dxcc_name)

        if call_info.cq_zone:
            is_new_zone = self.is_new_cq_zone(call_info.cq_zone)

        return is_new_dxcc or is_new_zone

    def _check_cqwpx_mult(
        self,
        callsign: str,
        call_info: Optional[CallInfo]
    ) -> bool:
        """Check CQWPX multiplier (prefixes)."""
        # CQWPX: Prefixes are multipliers
        return self.is_new_prefix(callsign)

    def _check_salmon_run_mult(
        self,
        callsign: str,
        call_info: Optional[CallInfo]
    ) -> bool:
        """Check Salmon Run multiplier (WA counties + DXCCs)."""
        if not call_info:
            return False

        # In-state: Counties are multipliers
        if call_info.state == "WA" and call_info.county:
            return self.is_new_county(call_info.county)

        # Out-of-state/DX: States/provinces/countries
        if call_info.state:
            return self.is_new_section(call_info.state)

        if call_info.dxcc_name:
            return self.is_new_dxcc(call_info.dxcc_name)

        return False

    def _extract_prefix(self, callsign: str) -> Optional[str]:
        """
        Extract callsign prefix for WPX.

        Args:
            callsign: Callsign to parse

        Returns:
            Prefix string or None

        Example:
            >>> _extract_prefix("W1AW")
            'W1'
            >>> _extract_prefix("K7ABC")
            'K7'
            >>> _extract_prefix("VE3XYZ")
            'VE3'
        """
        # Remove portable indicators
        call = re.sub(r'/[A-Z0-9]+$', '', callsign.upper())

        # Match prefix pattern: letters + digit
        match = re.match(r'^([A-Z0-9]*[A-Z]+\d+)', call)

        if match:
            return match.group(1)

        return None

    def get_statistics(self) -> dict:
        """
        Get multiplier statistics.

        Returns:
            Dictionary with statistics
        """
        return {
            'sections': len(self.worked_sections),
            'dxcc': len(self.worked_dxcc),
            'cq_zones': len(self.worked_cq_zones),
            'prefixes': len(self.worked_prefixes),
            'counties': len(self.worked_counties),
            'contest_type': self.contest_type.value,
        }

    def reset(self):
        """Reset all worked multipliers."""
        self.worked_sections.clear()
        self.worked_dxcc.clear()
        self.worked_cq_zones.clear()
        self.worked_prefixes.clear()
        self.worked_counties.clear()

        logger.info("Multiplier tracker reset")

    def __repr__(self) -> str:
        """String representation."""
        stats = self.get_statistics()
        return (
            f"MultiplierTracker("
            f"sections={stats['sections']}, "
            f"dxcc={stats['dxcc']}, "
            f"zones={stats['cq_zones']}, "
            f"prefixes={stats['prefixes']})"
        )
