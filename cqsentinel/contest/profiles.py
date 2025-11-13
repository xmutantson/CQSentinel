"""
Contest profile definitions.

Pre-configured profiles for major amateur radio contests with
exchange parsing, multiplier tracking, and contest-specific logic.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class MultiplierType(Enum):
    """Multiplier scoring type."""
    ADDITIVE = "additive"  # Score = QSOs + mults
    MULTIPLICATIVE = "multiplicative"  # Score = QSOs × mults


@dataclass
class ExchangeField:
    """
    Contest exchange field definition.

    Defines a single field in the contest exchange (e.g., "class", "section").
    """
    name: str  # Field name (e.g., "class", "section", "zone")
    description: str  # Human-readable description
    regex: str  # Regex pattern for this field
    required: bool = True  # Is this field required?
    examples: List[str] = field(default_factory=list)  # Example values

    def validate(self, value: str) -> bool:
        """
        Validate field value against regex.

        Args:
            value: Value to validate

        Returns:
            True if valid
        """
        return bool(re.match(self.regex, value, re.IGNORECASE))


@dataclass
class ContestProfile:
    """
    Contest profile with exchange, multipliers, and detection.

    Defines all contest-specific parameters for automated detection
    and parsing.
    """
    # Basic info
    name: str
    short_name: str  # "FD", "WFD", "CQWW", etc.
    description: str = ""

    # Exchange parsing
    exchange_fields: List[ExchangeField] = field(default_factory=list)
    exchange_regex: str = ""  # Complete exchange pattern

    # Keywords for detection
    keywords: List[str] = field(default_factory=list)  # Contest keywords
    cq_phrases: List[str] = field(default_factory=list)  # CQ phrases

    # Multipliers
    mult_type: MultiplierType = MultiplierType.ADDITIVE
    mult_fields: List[str] = field(default_factory=list)  # Which fields are mults
    mult_values: Dict[str, Set[str]] = field(default_factory=dict)  # Valid mult values

    # Phonetic variations (contest-specific)
    custom_phonetics: Dict[str, str] = field(default_factory=dict)

    # Scoring (optional)
    points_per_qso: int = 1

    # Band/mode restrictions (optional)
    bands: Optional[List[str]] = None  # None = all bands
    modes: Optional[List[str]] = None  # None = all modes

    def parse_exchange(self, text: str) -> Optional[Dict[str, str]]:
        """
        Parse exchange from text.

        Args:
            text: Text containing exchange

        Returns:
            Dictionary of field name → value, or None if not parseable
        """
        if not self.exchange_regex:
            return None

        match = re.search(self.exchange_regex, text, re.IGNORECASE)
        if not match:
            return None

        # Map groups to field names
        result = {}
        groups = match.groups()

        if len(groups) != len(self.exchange_fields):
            logger.warning(
                f"Exchange regex returned {len(groups)} groups, "
                f"expected {len(self.exchange_fields)}"
            )
            return None

        for i, field_def in enumerate(self.exchange_fields):
            value = groups[i]
            if value:
                result[field_def.name] = value.upper()

        return result

    def is_multiplier(self, field_name: str, value: str) -> bool:
        """
        Check if value is a new multiplier.

        Args:
            field_name: Field name (e.g., "section")
            value: Value to check (e.g., "CT")

        Returns:
            True if field is a multiplier type and value is valid
        """
        if field_name not in self.mult_fields:
            return False

        # Check against valid values (if defined)
        if field_name in self.mult_values:
            return value.upper() in self.mult_values[field_name]

        # No restriction - all values are valid
        return True

    def extract_multipliers(self, exchange: Dict[str, str]) -> List[Tuple[str, str]]:
        """
        Extract all multipliers from parsed exchange.

        Args:
            exchange: Parsed exchange dictionary

        Returns:
            List of (field_name, value) tuples for multipliers
        """
        mults = []
        for field_name in self.mult_fields:
            if field_name in exchange:
                value = exchange[field_name]
                if self.is_multiplier(field_name, value):
                    mults.append((field_name, value))
        return mults

    def matches_contest(self, text: str) -> bool:
        """
        Check if text indicates this contest.

        Args:
            text: Transcript text

        Returns:
            True if contest keywords detected
        """
        text_lower = text.lower()

        # Check contest keywords
        for keyword in self.keywords:
            if keyword.lower() in text_lower:
                return True

        # Check CQ phrases
        for phrase in self.cq_phrases:
            if phrase.lower() in text_lower:
                return True

        return False


# =============================================================================
# ARRL Field Day
# =============================================================================

# ARRL/RAC sections (83 total)
ARRL_SECTIONS = {
    # US States
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    # Multi-section states
    "EB", "LAX", "ORG", "SB", "SCV", "SDG", "SF", "SJV", "SV", "PAC",  # CA
    "EMA", "WMA",  # MA
    "ENY", "NLI", "NNJ", "NNY", "SNJ", "WNY",  # NY/NJ splits
    "EPA", "WPA",  # PA
    "NFL", "SFL", "WCF",  # FL
    "NTX", "STX", "WTX",  # TX
    # Canadian sections
    "AB", "BC", "MB", "NB", "NL", "NT", "NS", "NU", "ON", "PE", "QC", "SK", "YT",
    # Maritime
    "MAR",
    # DX
    "DX"
}

FIELD_DAY = ContestProfile(
    name="ARRL Field Day",
    short_name="FD",
    description="Annual emergency preparedness exercise, 4th full weekend in June",

    # Exchange: Class (e.g., "2A") + Section (e.g., "CT")
    exchange_fields=[
        ExchangeField(
            name="class",
            description="Operating class (number + letter)",
            regex=r"\d+[A-F]",
            examples=["1A", "2A", "3A", "1B", "2F"]
        ),
        ExchangeField(
            name="section",
            description="ARRL/RAC section",
            regex=r"[A-Z]{2,3}",
            examples=["CT", "MA", "WA", "ON", "DX"]
        )
    ],
    exchange_regex=r"(\d+[A-F])\s+([A-Z]{2,3})",

    # Detection keywords
    keywords=[
        "field day",
        "class",
        "section",
        "emergency",
        "FD"
    ],
    cq_phrases=[
        "CQ Field Day",
        "CQ FD"
    ],

    # Multipliers
    mult_type=MultiplierType.ADDITIVE,
    mult_fields=["section"],
    mult_values={"section": ARRL_SECTIONS},

    # Custom phonetics
    custom_phonetics={
        "kilowatt": "K",  # Common for K
        "ocean": "O",     # Common for O
        "america": "A",   # Common for A
    },

    # Scoring
    points_per_qso=1,

    # No band/mode restrictions
    bands=None,
    modes=["SSB", "CW", "DIGITAL"]
)

# =============================================================================
# Winter Field Day
# =============================================================================

WINTER_FIELD_DAY = ContestProfile(
    name="Winter Field Day",
    short_name="WFD",
    description="Winter emergency preparedness exercise, last full weekend in January",

    # Exchange: Class (e.g., "2O") + Section
    exchange_fields=[
        ExchangeField(
            name="class",
            description="Operating class (number + O/I)",
            regex=r"\d+[OI]",
            examples=["1O", "2O", "3I", "1I"]
        ),
        ExchangeField(
            name="section",
            description="ARRL/RAC section",
            regex=r"[A-Z]{2,3}",
            examples=["CT", "MA", "WA", "ON", "DX"]
        )
    ],
    exchange_regex=r"(\d+[OI])\s+([A-Z]{2,3})",

    # Detection keywords
    keywords=[
        "winter field day",
        "wfd",
        "class",
        "section",
        "outdoor",
        "indoor"
    ],
    cq_phrases=[
        "CQ Winter Field Day",
        "CQ WFD"
    ],

    # Multipliers
    mult_type=MultiplierType.ADDITIVE,
    mult_fields=["section"],
    mult_values={"section": ARRL_SECTIONS},

    # Custom phonetics
    custom_phonetics={
        "india": "I",     # Indoor
        "ocean": "O",     # Outdoor
        "outdoor": "O",
        "indoor": "I"
    },

    # Scoring
    points_per_qso=1,

    # No band/mode restrictions
    bands=None,
    modes=["SSB", "CW", "DIGITAL"]
)

# =============================================================================
# CQ World Wide DX Contest
# =============================================================================

# CQ Zones (1-40)
CQ_ZONES = {str(i) for i in range(1, 41)}

CQ_WW_DX = ContestProfile(
    name="CQ World Wide DX Contest",
    short_name="CQWW",
    description="World's largest DX contest, last full weekend of October (SSB) and November (CW)",

    # Exchange: RST + CQ Zone
    exchange_fields=[
        ExchangeField(
            name="rst",
            description="Signal report",
            regex=r"5[79]9?",
            examples=["59", "599", "57", "579"]
        ),
        ExchangeField(
            name="cq_zone",
            description="CQ Zone (1-40)",
            regex=r"\d{1,2}",
            examples=["5", "14", "25", "33"]
        )
    ],
    exchange_regex=r"(5[79]9?)\s+(\d{1,2})",

    # Detection keywords
    keywords=[
        "cq world wide",
        "cq ww",
        "zone",
        "cqww"
    ],
    cq_phrases=[
        "CQ WW",
        "CQ Contest",
        "CQ DX"
    ],

    # Multipliers: CQ zones + DXCC countries
    mult_type=MultiplierType.MULTIPLICATIVE,
    mult_fields=["cq_zone", "country"],
    mult_values={"cq_zone": CQ_ZONES},
    # Countries validated via N3FJP/DXCC lookup

    # No custom phonetics
    custom_phonetics={},

    # Scoring (varies by distance)
    points_per_qso=3,  # Simplified; actual varies

    # No band/mode restrictions
    bands=None,
    modes=["SSB", "CW"]
)

# =============================================================================
# CQ WPX Contest
# =============================================================================

CQ_WPX = ContestProfile(
    name="CQ WPX Contest",
    short_name="CQWPX",
    description="CQ magazine Worked All Prefixes contest, last full weekend of March (SSB) and May (CW)",

    # Exchange: RST + Serial number
    exchange_fields=[
        ExchangeField(
            name="rst",
            description="Signal report",
            regex=r"5[79]9?",
            examples=["59", "599", "57", "579"]
        ),
        ExchangeField(
            name="serial",
            description="Serial number",
            regex=r"\d{1,4}",
            examples=["001", "123", "1234"]
        )
    ],
    exchange_regex=r"(5[79]9?)\s+(\d{1,4})",

    # Detection keywords
    keywords=[
        "wpx",
        "worked all prefixes",
        "serial",
        "cq wpx"
    ],
    cq_phrases=[
        "CQ WPX",
        "CQ Contest"
    ],

    # Multipliers: Unique callsign prefixes
    mult_type=MultiplierType.MULTIPLICATIVE,
    mult_fields=["prefix"],
    mult_values={},  # Prefixes computed dynamically from callsigns

    # No custom phonetics
    custom_phonetics={},

    # Scoring
    points_per_qso=1,

    # No band/mode restrictions
    bands=None,
    modes=["SSB", "CW", "DIGITAL"]
)

# =============================================================================
# Washington State Salmon Run
# =============================================================================

# WA Counties (39 total)
WA_COUNTIES = {
    "ADAMS", "ASOTIN", "BENTON", "CHELAN", "CLALLAM", "CLARK",
    "COLUMBIA", "COWLITZ", "DOUGLAS", "FERRY", "FRANKLIN",
    "GARFIELD", "GRANT", "GRAYS HARBOR", "GRAYS", "ISLAND", "JEFFERSON",
    "KING", "KITSAP", "KITTITAS", "KLICKITAT", "LEWIS", "LINCOLN",
    "MASON", "OKANOGAN", "PACIFIC", "PEND OREILLE", "PEND", "PIERCE",
    "SAN JUAN", "SAN", "SKAGIT", "SKAMANIA", "SNOHOMISH", "SPOKANE",
    "STEVENS", "THURSTON", "WAHKIAKUM", "WALLA WALLA", "WALLA", "WHATCOM",
    "WHITMAN", "YAKIMA",
    # Abbreviations
    "GH", "PO", "SJ", "WW"
}

SALMON_RUN = ContestProfile(
    name="Washington State Salmon Run",
    short_name="WASR",
    description="Annual Washington state QSO party, first full weekend in October",

    # Exchange: RST + QTH (county for WA, state/province/DX for others)
    exchange_fields=[
        ExchangeField(
            name="rst",
            description="Signal report",
            regex=r"5[79]9?",
            examples=["59", "599", "57", "579"]
        ),
        ExchangeField(
            name="qth",
            description="County (WA) or State/Province/DX",
            regex=r"[A-Z]{2,12}",
            examples=["KING", "PIERCE", "OR", "CA", "DX"]
        )
    ],
    exchange_regex=r"(5[79]9?)\s+([A-Z]{2,12})",

    # Detection keywords
    keywords=[
        "salmon run",
        "washington",
        "county",
        "wasr"
    ],
    cq_phrases=[
        "CQ Salmon Run",
        "CQ WASR",
        "CQ Washington"
    ],

    # Multipliers: WA counties (in-state) + states/provinces (out-of-state)
    mult_type=MultiplierType.ADDITIVE,
    mult_fields=["county", "state"],
    mult_values={"county": WA_COUNTIES},
    # States/provinces validated via standard lists

    # No custom phonetics
    custom_phonetics={},

    # Scoring
    points_per_qso=1,

    # No band/mode restrictions
    bands=None,
    modes=["SSB", "CW", "DIGITAL"]
)

# =============================================================================
# Profile Registry
# =============================================================================

# All available contest profiles
CONTEST_PROFILES: Dict[str, ContestProfile] = {
    "field_day": FIELD_DAY,
    "winter_field_day": WINTER_FIELD_DAY,
    "cqww": CQ_WW_DX,
    "cqwpx": CQ_WPX,
    "salmon_run": SALMON_RUN,
}

# Short name lookup
CONTEST_PROFILES_BY_SHORT_NAME: Dict[str, ContestProfile] = {
    profile.short_name.lower(): profile
    for profile in CONTEST_PROFILES.values()
}


def get_contest_profile(name: str) -> Optional[ContestProfile]:
    """
    Get contest profile by name or short name.

    Args:
        name: Profile name (e.g., "field_day", "FD", "CQWW")

    Returns:
        ContestProfile or None if not found
    """
    name_lower = name.lower()

    # Try full name first
    if name_lower in CONTEST_PROFILES:
        return CONTEST_PROFILES[name_lower]

    # Try short name
    if name_lower in CONTEST_PROFILES_BY_SHORT_NAME:
        return CONTEST_PROFILES_BY_SHORT_NAME[name_lower]

    return None


def list_contest_profiles() -> List[str]:
    """Get list of available contest profile names."""
    return list(CONTEST_PROFILES.keys())


def detect_contest(text: str) -> Optional[ContestProfile]:
    """
    Auto-detect contest from transcript text.

    Args:
        text: Transcript text

    Returns:
        Best matching ContestProfile or None
    """
    # Score each profile
    scores = {}
    for name, profile in CONTEST_PROFILES.items():
        if profile.matches_contest(text):
            # Count keyword matches
            text_lower = text.lower()
            score = sum(
                1 for keyword in profile.keywords
                if keyword.lower() in text_lower
            )
            score += sum(
                2 for phrase in profile.cq_phrases
                if phrase.lower() in text_lower
            )
            scores[name] = score

    if not scores:
        return None

    # Return highest scoring profile
    best_name = max(scores.items(), key=lambda x: x[1])[0]
    return CONTEST_PROFILES[best_name]


def parse_exchange_auto(text: str, contest: Optional[str] = None) -> Optional[Dict[str, str]]:
    """
    Parse exchange from text with optional contest hint.

    Args:
        text: Text containing exchange
        contest: Optional contest name/short name

    Returns:
        Parsed exchange dictionary or None
    """
    if contest:
        # Use specific contest
        profile = get_contest_profile(contest)
        if profile:
            return profile.parse_exchange(text)
        logger.warning(f"Unknown contest: {contest}")
        return None

    # Try all contests
    for profile in CONTEST_PROFILES.values():
        result = profile.parse_exchange(text)
        if result:
            logger.info(f"Detected {profile.name} exchange: {result}")
            return result

    return None
