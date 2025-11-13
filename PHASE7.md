# Phase 7: N3FJP Integration

**Status**: ✅ Complete
**Date**: 2025-01-13

## Overview

Phase 7 implements **N3FJP integration** - connecting to N3FJP logging software for real-time dupe checking and multiplier detection. This prevents duplicate contacts and highlights new multipliers on the band map.

### Key Features

- **TCP API client** - Connects to N3FJP on port 1100
- **Dupe checking** - Real-time check if callsign already worked
- **Callsign information** - DXCC, zone, grid, state/county lookup
- **Multiplier detection** - Identifies new multipliers by contest type
- **Auto-reconnect** - Automatic reconnection on disconnect
- **Contest-aware** - Supports Field Day, CQWW, CQWPX, Salmon Run

---

## Architecture

### N3FJP Integration System

```
N3FJPClient → TCP socket connection (port 1100)
     ↓
Commands → <CMD>...</CMD> XML-like format
     ↓
Responses → Parsed for dupe/multiplier info
     ↓
MultiplierTracker → Contest-specific multiplier logic
     ↓
Band Map Updates → Mark dupes and multipliers
```

### Components

1. **N3FJPClient** - TCP API client with auto-reconnect
2. **CallInfo** - Callsign information dataclass
3. **MultiplierTracker** - Contest multiplier tracking
4. **ContestType** - Enum for different contests

---

## N3FJP Client

### N3FJPClient Class

TCP client for N3FJP logging software:

**Features:**
- Asynchronous connection with timeout
- Auto-reconnect on disconnect
- Thread-safe operations
- XML-like command protocol
- Error handling and recovery

### Connection Management

```python
from cqsentinel.n3fjp import N3FJPClient

# Connect to N3FJP
client = N3FJPClient(host='localhost', port=1100)

if client.connect():
    print("Connected to N3FJP!")
else:
    print("Connection failed")

# Check connection status
if client.is_connected():
    print("Still connected")

# Disconnect
client.disconnect()
```

### Context Manager

```python
# Automatic connection/disconnection
with N3FJPClient() as client:
    is_dupe = client.check_dupe('W1AW')
    # Automatically disconnects on exit
```

---

## Dupe Checking

### check_dupe() Method

Check if a callsign has already been worked:

```python
from cqsentinel.n3fjp import N3FJPClient

client = N3FJPClient()
client.connect()

# Basic dupe check
is_dupe = client.check_dupe('W1AW')
if is_dupe:
    print("Already worked W1AW - DUPE!")

# Band/mode specific
is_dupe_20m = client.check_dupe('W1AW', band='20m', mode='SSB')
if not is_dupe_20m:
    print("New on 20m SSB")
```

### Command Format

N3FJP uses XML-like command format:

```xml
<CMD><CHECKDUPE><CALL>W1AW</CALL><BAND>20m</BAND><MODE>SSB</MODE></CHECKDUPE></CMD>
```

Response indicates DUPE or NEW.

---

## Callsign Information

### get_call_info() Method

Get comprehensive information about a callsign:

```python
from cqsentinel.n3fjp import N3FJPClient

client = N3FJPClient()
client.connect()

info = client.get_call_info('W1AW')

print(f"Callsign: {info.callsign}")
print(f"DXCC: {info.dxcc_name}")  # "United States"
print(f"State: {info.state}")     # "CT"
print(f"Grid: {info.grid}")       # "FN31"
print(f"CQ Zone: {info.cq_zone}") # "5"
print(f"Continent: {info.continent}")  # "NA"
print(f"Is Dupe: {info.is_dupe}") # True/False
```

### CallInfo Dataclass

```python
@dataclass
class CallInfo:
    callsign: str
    is_dupe: bool = False
    is_mult: bool = False

    # DXCC info
    dxcc_name: Optional[str] = None      # "United States"
    dxcc_entity: Optional[str] = None    # "K"
    continent: Optional[str] = None       # "NA"

    # Zone info
    cq_zone: Optional[str] = None        # "5"
    itu_zone: Optional[str] = None       # "8"

    # Location
    grid: Optional[str] = None           # "FN31"
    state: Optional[str] = None          # "CT"
    county: Optional[str] = None         # "Hartford"

    # Previous QSO
    prev_band: Optional[str] = None
    prev_mode: Optional[str] = None
    prev_datetime: Optional[str] = None
```

---

## Multiplier Detection

### MultiplierTracker Class

Contest-aware multiplier tracking:

**Supported Contests:**
- **Field Day**: ARRL/RAC sections (83 total)
- **Winter Field Day**: Same as Field Day
- **CQWW**: DXCC entities + CQ zones (1-40)
- **CQWPX**: Callsign prefixes
- **Salmon Run**: WA counties (39) + states/DX

### Basic Usage

```python
from cqsentinel.n3fjp import MultiplierTracker, ContestType, CallInfo

# Create tracker for Field Day
tracker = MultiplierTracker(contest_type=ContestType.FIELD_DAY)

# Check if new multiplier
call_info = CallInfo(callsign="W1AW", state="CT")

if tracker.is_new_multiplier("W1AW", call_info):
    print("New section multiplier: CT")
    tracker.mark_worked("W1AW", call_info)
```

### Contest-Specific Multipliers

**Field Day / Winter Field Day:**
```python
tracker = MultiplierTracker(ContestType.FIELD_DAY)

# Sections are multipliers
tracker.mark_worked_section("CT")
tracker.mark_worked_section("MA")

if tracker.is_new_section("NY"):
    print("New section: NY")
```

**CQWW:**
```python
tracker = MultiplierTracker(ContestType.CQWW)

# Both DXCC and zones are multipliers
call_info = CallInfo(
    callsign="G4ABC",
    dxcc_name="England",
    cq_zone="14"
)

is_new = tracker.is_new_multiplier("G4ABC", call_info)
# Checks both DXCC and zone
```

**CQWPX:**
```python
tracker = MultiplierTracker(ContestType.CQWPX)

# Prefixes are multipliers
if tracker.is_new_prefix("W1AW"):  # Prefix: W1
    print("New prefix: W1")

if tracker.is_new_prefix("K7ABC"):  # Prefix: K7
    print("New prefix: K7")
```

**Salmon Run:**
```python
tracker = MultiplierTracker(ContestType.SALMON_RUN)

# WA counties are multipliers (in-state)
call_info = CallInfo(callsign="W7XYZ", state="WA", county="King")
if tracker.is_new_county("King"):
    print("New WA county: King")

# States/DX are multipliers (out-of-state)
call_info = CallInfo(callsign="W1AW", state="CT")
if tracker.is_new_section("CT"):
    print("New state: CT")
```

### Tracking Methods

```python
# Check methods
tracker.is_new_section("CT")
tracker.is_new_dxcc("United States")
tracker.is_new_cq_zone("5")
tracker.is_new_prefix("W1")
tracker.is_new_county("King")

# Mark as worked
tracker.mark_worked_section("CT")
tracker.mark_worked_dxcc("United States")
tracker.mark_worked_cq_zone("5")
tracker.mark_worked_prefix("W1AW")
tracker.mark_worked_county("King")

# Mark all from call_info
tracker.mark_worked("W1AW", call_info)

# Statistics
stats = tracker.get_statistics()
print(f"Sections: {stats['sections']}")
print(f"DXCC: {stats['dxcc']}")
print(f"Zones: {stats['cq_zones']}")
print(f"Prefixes: {stats['prefixes']}")

# Reset all
tracker.reset()
```

---

## Integration Example

### Complete Integration with Band Map

```python
from cqsentinel.n3fjp import N3FJPClient, MultiplierTracker, ContestType
from cqsentinel.bandmap import BandMapState, StationStatus

# Initialize
n3fjp = N3FJPClient()
n3fjp.connect()

tracker = MultiplierTracker(ContestType.FIELD_DAY)
band_map = BandMapState(band="20m")

# Process detected station
def process_station(frequency, callsign):
    # Get callsign info from N3FJP
    call_info = n3fjp.get_call_info(callsign)

    # Check dupe
    is_dupe = call_info.is_dupe

    # Check multiplier
    is_mult = tracker.is_new_multiplier(callsign, call_info)

    # Determine status
    if is_dupe:
        status = StationStatus.WORKED
    elif is_mult:
        status = StationStatus.MULTIPLIER
    else:
        status = StationStatus.NEW

    # Add to band map
    station = band_map.add_or_update_station(
        frequency=frequency,
        callsign=callsign,
        status=status,
        is_multiplier=is_mult,
        worked=is_dupe,
        exchange=call_info.state,  # For Field Day
        section=call_info.state
    )

    # Log result
    if is_mult:
        print(f"NEW MULTIPLIER: {callsign} - {call_info.state}")
    elif is_dupe:
        print(f"DUPE: {callsign}")
    else:
        print(f"NEW: {callsign}")

    return station

# Example usage
station = process_station(14250000, "W1AW")
```

### Continuous Monitoring

```python
import time

def monitor_band_map():
    """Continuously update band map with N3FJP status."""

    while True:
        # Get all unworked stations from band map
        new_stations = band_map.get_new_stations()

        for station in new_stations:
            if not station.callsign:
                continue

            # Update status from N3FJP
            call_info = n3fjp.get_call_info(station.callsign)

            if call_info.is_dupe:
                station.status = StationStatus.WORKED
                station.worked = True

            # Check multiplier
            if tracker.is_new_multiplier(station.callsign, call_info):
                station.status = StationStatus.MULTIPLIER
                station.is_multiplier = True

        time.sleep(5)  # Update every 5 seconds

# Run in background thread
import threading
monitor_thread = threading.Thread(target=monitor_band_map, daemon=True)
monitor_thread.start()
```

---

## Additional Features

### Frequency Control

```python
# Get current frequency from N3FJP
freq_hz = client.get_frequency()
print(f"N3FJP frequency: {freq_hz/1e6:.3f} MHz")

# Set frequency in N3FJP
client.set_frequency(14250000)  # 14.250 MHz
```

### Adding Contacts

```python
# Log a contact in N3FJP
success = client.add_contact(
    callsign="W1AW",
    freq_hz=14250000,
    mode="SSB",
    rst_sent="59",
    rst_rcvd="59",
    exchange="2A CT"
)

if success:
    print("Contact logged successfully")

    # Mark as worked
    tracker.mark_worked_section("CT")
```

---

## Error Handling

### Connection Errors

```python
client = N3FJPClient(auto_reconnect=True)

if not client.connect():
    print("Initial connection failed")
    # Auto-reconnect will retry in background

# Check status
from cqsentinel.n3fjp import N3FJPStatus

if client.status == N3FJPStatus.CONNECTED:
    print("Connected")
elif client.status == N3FJPStatus.CONNECTING:
    print("Connecting...")
elif client.status == N3FJPStatus.ERROR:
    print("Error - auto-reconnect active")
```

### Command Timeouts

```python
client = N3FJPClient(timeout=10.0)  # 10 second timeout

response = client.send_command("<CMD>...</CMD>")
if response is None:
    print("Command timed out or failed")
```

---

## Files Created

### New Files

1. **cqsentinel/n3fjp/client.py** (550 lines)
   - N3FJPClient class
   - TCP socket management
   - Command/response handling
   - Auto-reconnect logic
   - CallInfo dataclass
   - N3FJPStatus enum

2. **cqsentinel/n3fjp/multipliers.py** (400 lines)
   - MultiplierTracker class
   - Contest-specific multiplier logic
   - ContestType enum
   - ARRL_SECTIONS (83 sections)
   - WA_COUNTIES (39 counties)
   - Prefix extraction for WPX

3. **cqsentinel/n3fjp/__init__.py**
   - Module exports

---

## Summary

Phase 7 adds **N3FJP logging integration** to CQSentinel:

✅ **TCP API client** - Full-featured N3FJP connection
✅ **Dupe checking** - Real-time dupe detection
✅ **Callsign info** - DXCC, zone, state, grid lookup
✅ **Multiplier tracking** - Contest-aware multiplier detection
✅ **Auto-reconnect** - Automatic reconnection on disconnect
✅ **5 contests supported** - Field Day, WFD, CQWW, CQWPX, Salmon Run
✅ **Thread-safe** - Safe for multi-threaded use
✅ **Error handling** - Robust error recovery

**Result**: CQSentinel can now **distinguish dupes from new contacts** and **highlight new multipliers** in real-time using N3FJP's contest log.

**Ready for Phase 8: Band Scanning Engine** 🔄
