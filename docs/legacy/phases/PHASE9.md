# Phase 9: Contest Profiles

**Status**: ✅ Complete
**Date**: 2025-01-13

## Overview

Phase 9 implements **contest-specific profiles** - pre-configured settings for 5 major amateur radio contests with automatic exchange parsing, multiplier tracking, and contest detection.

### Key Features

- **5 pre-configured contests** - Field Day, Winter Field Day, CQWW, CQWPX, Salmon Run
- **Exchange parsing** - Regex-based exchange field extraction
- **Auto-detection** - Identify contest from transcript keywords
- **Multiplier definitions** - Contest-specific multiplier rules
- **Custom phonetics** - Contest-specific phonetic variations
- **Flexible API** - Easy to add new contests

---

## Architecture

### Contest Profile System

```
ContestProfile
    ↓
Exchange Fields → Parse RST, Zone, Section, Serial, etc.
    ↓
Multiplier Rules → Sections, Zones, Prefixes, Counties
    ↓
Detection Keywords → Auto-identify contest from transcript
    ↓
Custom Phonetics → Contest-specific variations
    ↓
Scoring Rules → Points per QSO, multiplier type
```

### Components

1. **ContestProfile** - Complete contest definition
2. **ExchangeField** - Individual exchange field with validation
3. **MultiplierType** - ADDITIVE vs MULTIPLICATIVE scoring
4. **Auto-detection** - Keyword-based contest identification
5. **Exchange parser** - Regex-based field extraction

---

## ContestProfile Data Structure

### Core Fields

```python
@dataclass
class ContestProfile:
    # Basic info
    name: str               # "ARRL Field Day"
    short_name: str         # "FD"
    description: str        # Contest description

    # Exchange parsing
    exchange_fields: List[ExchangeField]
    exchange_regex: str     # Complete exchange pattern

    # Detection
    keywords: List[str]     # Contest keywords
    cq_phrases: List[str]   # CQ phrases

    # Multipliers
    mult_type: MultiplierType
    mult_fields: List[str]  # Which fields are mults
    mult_values: Dict[str, Set[str]]  # Valid mult values

    # Phonetics
    custom_phonetics: Dict[str, str]

    # Scoring
    points_per_qso: int

    # Restrictions (optional)
    bands: Optional[List[str]]
    modes: Optional[List[str]]
```

### ExchangeField Definition

```python
@dataclass
class ExchangeField:
    name: str          # "class", "section", "zone", etc.
    description: str   # Human-readable description
    regex: str         # Validation regex
    required: bool     # Is field required?
    examples: List[str]  # Example values
```

---

## Pre-Configured Contests

### 1. ARRL Field Day

**Exchange**: Class (e.g., "2A") + Section (e.g., "CT")

```python
from cqsentinel.contest import FIELD_DAY

# Profile details
print(f"Name: {FIELD_DAY.name}")
print(f"Short: {FIELD_DAY.short_name}")
print(f"Exchange: {[f.name for f in FIELD_DAY.exchange_fields]}")
# Exchange: ['class', 'section']

# Parse exchange
result = FIELD_DAY.parse_exchange("You are 2A CT")
print(result)
# {'class': '2A', 'section': 'CT'}

# Check multiplier
is_mult = FIELD_DAY.is_multiplier("section", "CT")
print(f"CT is multiplier: {is_mult}")  # True

# Extract all multipliers from exchange
mults = FIELD_DAY.extract_multipliers(result)
print(mults)
# [('section', 'CT')]
```

**Multipliers**: ARRL/RAC sections (83 total)
- 50 US states (+ multi-section states)
- 13 Canadian provinces/territories
- DX

**Keywords**: "field day", "class", "section", "emergency", "FD"

**CQ Phrases**: "CQ Field Day", "CQ FD"

**Custom Phonetics**: kilowatt→K, ocean→O, america→A

---

### 2. Winter Field Day

**Exchange**: Class (e.g., "2O") + Section

```python
from cqsentinel.contest import WINTER_FIELD_DAY

# Parse exchange
result = WINTER_FIELD_DAY.parse_exchange("You are 3I MA")
print(result)
# {'class': '3I', 'section': 'MA'}
```

**Class Letters**:
- **O** = Outdoor
- **I** = Indoor

**Multipliers**: Same 83 ARRL/RAC sections as Field Day

**Keywords**: "winter field day", "wfd", "outdoor", "indoor"

**Custom Phonetics**: india→I, ocean→O, outdoor→O, indoor→I

---

### 3. CQ World Wide DX Contest

**Exchange**: RST (e.g., "59") + CQ Zone (1-40)

```python
from cqsentinel.contest import CQ_WW_DX

# Parse exchange
result = CQ_WW_DX.parse_exchange("You are 59 14")
print(result)
# {'rst': '59', 'cq_zone': '14'}

# Check zone multiplier
is_mult = CQ_WW_DX.is_multiplier("cq_zone", "14")
print(f"Zone 14 is multiplier: {is_mult}")  # True
```

**Multipliers**:
- **CQ Zones**: 1-40
- **DXCC Countries**: Validated via N3FJP

**Multiplier Type**: MULTIPLICATIVE (QSOs × zones × countries)

**Keywords**: "cq world wide", "cq ww", "zone", "cqww"

**CQ Phrases**: "CQ WW", "CQ Contest", "CQ DX"

---

### 4. CQ WPX Contest

**Exchange**: RST + Serial Number

```python
from cqsentinel.contest import CQ_WPX

# Parse exchange
result = CQ_WPX.parse_exchange("You are 599 0123")
print(result)
# {'rst': '599', 'serial': '0123'}
```

**Multipliers**: Unique callsign **prefixes**
- W1, K7, G4, JA1, etc.
- Computed dynamically from worked callsigns

**Multiplier Type**: MULTIPLICATIVE (QSOs × prefixes)

**Keywords**: "wpx", "worked all prefixes", "serial", "cq wpx"

**CQ Phrases**: "CQ WPX", "CQ Contest"

---

### 5. Washington State Salmon Run

**Exchange**: RST + QTH
- **WA stations**: County (e.g., "KING", "PIERCE")
- **Non-WA stations**: State/Province (e.g., "OR", "CA", "BC")

```python
from cqsentinel.contest import SALMON_RUN

# Parse WA county exchange
result = SALMON_RUN.parse_exchange("You are 59 KING")
print(result)
# {'rst': '59', 'qth': 'KING'}

# Parse out-of-state exchange
result = SALMON_RUN.parse_exchange("You are 59 OR")
print(result)
# {'rst': '59', 'qth': 'OR'}

# Check county multiplier
is_mult = SALMON_RUN.is_multiplier("county", "KING")
print(f"KING is multiplier: {is_mult}")  # True
```

**Multipliers**:
- **In-state (WA)**: 39 WA counties
- **Out-of-state**: States/provinces/DX

**Keywords**: "salmon run", "washington", "county", "wasr"

**CQ Phrases**: "CQ Salmon Run", "CQ WASR", "CQ Washington"

---

## Using Contest Profiles

### Getting a Profile

```python
from cqsentinel.contest import get_contest_profile

# By full name
profile = get_contest_profile("field_day")

# By short name
profile = get_contest_profile("FD")

# Case insensitive
profile = get_contest_profile("CQWW")

if profile:
    print(f"Loaded: {profile.name}")
else:
    print("Profile not found")
```

### Listing Available Profiles

```python
from cqsentinel.contest import list_contest_profiles

profiles = list_contest_profiles()
print(profiles)
# ['field_day', 'winter_field_day', 'cqww', 'cqwpx', 'salmon_run']
```

### Auto-Detection

```python
from cqsentinel.contest import detect_contest

# Detect from transcript
transcript = "CQ Field Day CQ Field Day this is W1AW"
profile = detect_contest(transcript)

if profile:
    print(f"Detected: {profile.name}")
    # Detected: ARRL Field Day
```

**Detection Logic**:
1. Check all profiles for keyword matches
2. Score based on:
   - Keyword matches (1 point each)
   - CQ phrase matches (2 points each)
3. Return highest scoring profile

---

## Exchange Parsing

### Manual Parsing

```python
from cqsentinel.contest import FIELD_DAY

# Parse exchange from text
text = "You are 2A Connecticut"
result = FIELD_DAY.parse_exchange(text)

if result:
    print(f"Class: {result['class']}")    # 2A
    print(f"Section: {result['section']}")  # CT (extracted from "Connecticut")
else:
    print("Parse failed")
```

### Auto-Parsing (Try All Contests)

```python
from cqsentinel.contest import parse_exchange_auto

# Try all contest profiles
text = "You are 59 zone 14"
result = parse_exchange_auto(text)

if result:
    print(f"Parsed: {result}")
    # Parsed: {'rst': '59', 'cq_zone': '14'}
```

### Contest-Specific Parsing

```python
from cqsentinel.contest import parse_exchange_auto

# Parse with contest hint
result = parse_exchange_auto(
    "You are 599 0123",
    contest="CQWPX"
)

print(result)
# {'rst': '599', 'serial': '0123'}
```

---

## Multiplier Handling

### Checking Multipliers

```python
from cqsentinel.contest import FIELD_DAY

# Check if value is valid multiplier
is_mult = FIELD_DAY.is_multiplier("section", "CT")
print(f"CT is valid section: {is_mult}")  # True

is_mult = FIELD_DAY.is_multiplier("section", "XX")
print(f"XX is valid section: {is_mult}")  # False (not in ARRL_SECTIONS)
```

### Extracting Multipliers from Exchange

```python
from cqsentinel.contest import CQ_WW_DX

# Parse exchange
exchange = CQ_WW_DX.parse_exchange("59 14")

# Extract all multipliers
mults = CQ_WW_DX.extract_multipliers(exchange)
print(mults)
# [('cq_zone', '14')]

# For CQWW with country info
exchange_with_country = {
    'rst': '59',
    'cq_zone': '14',
    'country': 'England'  # Added from DXCC lookup
}
mults = CQ_WW_DX.extract_multipliers(exchange_with_country)
print(mults)
# [('cq_zone', '14'), ('country', 'England')]
```

---

## Integration with Band Scanner

### Contest-Aware Scanning

```python
from cqsentinel.contest import get_contest_profile, detect_contest
from cqsentinel.scanner import BandScanner

# Initialize scanner
scanner = BandScanner(...)

# Set contest profile
current_contest = get_contest_profile("field_day")

# In scan callback
def on_station_detected(station):
    # Extract transcript
    transcript = ' '.join(station.transcripts)

    # Auto-detect contest if not set
    if not current_contest:
        detected = detect_contest(transcript)
        if detected:
            print(f"Auto-detected: {detected.name}")
            current_contest = detected

    # Parse exchange
    if current_contest:
        exchange = current_contest.parse_exchange(transcript)
        if exchange:
            print(f"Exchange: {exchange}")

            # Check multipliers
            mults = current_contest.extract_multipliers(exchange)
            for field, value in mults:
                print(f"Multiplier: {field}={value}")
```

### Custom Phonetics Integration

```python
from cqsentinel.contest import FIELD_DAY, WINTER_FIELD_DAY
from cqsentinel.contest import PhoneticParser

# Add contest-specific phonetics
parser = PhoneticParser()

# Merge Field Day phonetics
parser.phonetics.update(FIELD_DAY.custom_phonetics)
# kilowatt→K, ocean→O, america→A

# Parse with custom phonetics
callsign = parser.parse_phonetic("kilo one alpha whisper")
print(callsign)  # K1AW
```

---

## Multiplier Type Comparison

### Additive Multipliers

**Used by**: Field Day, Winter Field Day, Salmon Run

**Formula**: Score = QSOs + Multipliers

```python
# Field Day example
qsos = 100
sections = 50  # Worked 50 sections

score = qsos + sections  # 150
```

### Multiplicative Multipliers

**Used by**: CQWW, CQWPX

**Formula**: Score = QSOs × Multipliers

```python
# CQWW example
qsos = 500
zones = 30
countries = 100

score = qsos * (zones + countries)  # 500 × 130 = 65,000
```

---

## Constants and Lookups

### ARRL Sections

```python
from cqsentinel.contest import ARRL_SECTIONS

print(len(ARRL_SECTIONS))  # 83

# Check if valid section
if "CT" in ARRL_SECTIONS:
    print("Connecticut is valid section")

# All sections
print(sorted(ARRL_SECTIONS))
# ['AB', 'AK', 'AL', ..., 'WY', 'YT']
```

### CQ Zones

```python
from cqsentinel.contest import CQ_ZONES

print(len(CQ_ZONES))  # 40

# Check if valid zone
if "14" in CQ_ZONES:
    print("Zone 14 is valid")

# All zones
print(sorted(CQ_ZONES, key=int))
# ['1', '2', '3', ..., '39', '40']
```

### WA Counties

```python
from cqsentinel.contest import WA_COUNTIES

print(len(WA_COUNTIES))  # 39 (+ abbreviations)

# Check county
if "KING" in WA_COUNTIES:
    print("King County is valid")

# Abbreviations supported
if "SJ" in WA_COUNTIES:
    print("SJ (San Juan) is valid")
```

---

## Adding New Contests

### Creating Custom Profile

```python
from cqsentinel.contest import ContestProfile, ExchangeField, MultiplierType

# Define exchange fields
fields = [
    ExchangeField(
        name="rst",
        description="Signal report",
        regex=r"5[79]9?",
        examples=["59", "599"]
    ),
    ExchangeField(
        name="name",
        description="Operator name",
        regex=r"[A-Z]{2,15}",
        examples=["JOHN", "MARY"]
    )
]

# Create profile
my_contest = ContestProfile(
    name="Example Contest",
    short_name="EX",
    description="An example contest",

    exchange_fields=fields,
    exchange_regex=r"(5[79]9?)\s+([A-Z]{2,15})",

    keywords=["example", "contest"],
    cq_phrases=["CQ Example"],

    mult_type=MultiplierType.ADDITIVE,
    mult_fields=["state"],
    mult_values={},

    custom_phonetics={},
    points_per_qso=1
)

# Use it
result = my_contest.parse_exchange("You are 59 JOHN")
print(result)
# {'rst': '59', 'name': 'JOHN'}
```

### Registering New Profile

```python
from cqsentinel.contest import CONTEST_PROFILES

# Add to global registry
CONTEST_PROFILES["example"] = my_contest

# Now available via get_contest_profile
profile = get_contest_profile("example")
```

---

## Integration Examples

### Complete Field Day Setup

```python
#!/usr/bin/env python3
"""
Field Day scanning with contest profile.
"""

from cqsentinel.contest import FIELD_DAY, ARRL_SECTIONS
from cqsentinel.scanner import BandScanner
from cqsentinel.n3fjp import MultiplierTracker, ContestType

# Set up contest
contest = FIELD_DAY
print(f"Contest: {contest.name}")
print(f"Exchange: {[f.name for f in contest.exchange_fields]}")
print(f"Multipliers: {contest.mult_fields}")
print(f"Sections: {len(ARRL_SECTIONS)}")

# Configure multiplier tracker for Field Day
mult_tracker = MultiplierTracker(ContestType.FIELD_DAY)

# Scanner callback
def on_station_detected(station):
    # Get transcript
    transcript = ' '.join(station.transcripts)

    # Parse exchange
    exchange = contest.parse_exchange(transcript)
    if not exchange:
        print(f"Could not parse exchange from: {transcript[:50]}...")
        return

    print(f"\nStation: {station.callsign}")
    print(f"Exchange: {exchange}")

    # Extract multipliers
    mults = contest.extract_multipliers(exchange)
    for field, value in mults:
        if mult_tracker.is_new_section(value):
            print(f"*** NEW MULTIPLIER: {field}={value} ***")
            mult_tracker.mark_worked_section(value)
        else:
            print(f"Already worked section: {value}")

    # Show stats
    stats = mult_tracker.get_statistics()
    print(f"Sections worked: {stats['sections']}/{len(ARRL_SECTIONS)}")

# Create scanner
scanner = BandScanner(
    # ... components ...
    on_station_detected=on_station_detected
)

# Start scan
from cqsentinel.scanner import get_band_profile
profile = get_band_profile("field_day_20m")
scanner.start_scan(
    freq_start=profile.freq_start,
    freq_end=profile.freq_end,
    step_size=profile.step_size
)

# Monitor
import time
while scanner.is_scanning():
    time.sleep(1)

print("\nScan complete!")
stats = mult_tracker.get_statistics()
print(f"Final sections: {stats['sections']}/{len(ARRL_SECTIONS)}")
```

---

## Exchange Validation

### Field Validation

```python
from cqsentinel.contest import FIELD_DAY

# Get field definition
class_field = FIELD_DAY.exchange_fields[0]  # "class"

# Validate values
print(class_field.validate("2A"))   # True
print(class_field.validate("10B"))  # True
print(class_field.validate("5G"))   # False (G not valid)
print(class_field.validate("ABC"))  # False (wrong format)

# Section field
section_field = FIELD_DAY.exchange_fields[1]

print(section_field.validate("CT"))   # True
print(section_field.validate("MA"))   # True
print(section_field.validate("ZZ"))   # True (regex matches, but not in ARRL_SECTIONS)
```

### Complete Exchange Validation

```python
def validate_exchange(contest, exchange):
    """Validate complete parsed exchange."""
    for field_def in contest.exchange_fields:
        field_name = field_def.name

        # Check if required field is present
        if field_def.required and field_name not in exchange:
            print(f"Missing required field: {field_name}")
            return False

        # Validate value
        if field_name in exchange:
            value = exchange[field_name]
            if not field_def.validate(value):
                print(f"Invalid {field_name}: {value}")
                return False

    return True

# Test
from cqsentinel.contest import FIELD_DAY

exchange = FIELD_DAY.parse_exchange("2A CT")
is_valid = validate_exchange(FIELD_DAY, exchange)
print(f"Exchange valid: {is_valid}")
```

---

## Files Created

### New Files

1. **cqsentinel/contest/profiles.py** (650 lines)
   - ContestProfile dataclass
   - ExchangeField dataclass
   - MultiplierType enum
   - 5 pre-configured contest profiles:
     - FIELD_DAY (ARRL Field Day)
     - WINTER_FIELD_DAY (Winter Field Day)
     - CQ_WW_DX (CQ World Wide)
     - CQ_WPX (CQ WPX)
     - SALMON_RUN (WA Salmon Run)
   - Profile management functions
   - Auto-detection logic
   - Constants: ARRL_SECTIONS, CQ_ZONES, WA_COUNTIES

2. **cqsentinel/contest/__init__.py** (updated)
   - Added profile exports

---

## Summary

Phase 9 adds **contest-specific profiles** to CQSentinel:

✅ **5 pre-configured contests** - Field Day, Winter Field Day, CQWW, CQWPX, Salmon Run
✅ **Exchange parsing** - Regex-based field extraction with validation
✅ **Auto-detection** - Identify contest from transcript keywords
✅ **Multiplier tracking** - Contest-specific multiplier definitions
✅ **Custom phonetics** - Contest-specific phonetic variations
✅ **Flexible API** - Easy to add new contests
✅ **Complete validation** - Exchange field validation
✅ **Integration ready** - Works with scanner, N3FJP, multiplier tracker

**Result**: CQSentinel can now **automatically detect contests**, **parse exchanges**, and **identify multipliers** for 5 major contests, with easy extensibility for adding more.

**Ready for Phase 10: Polish & Distribution** 🎉
