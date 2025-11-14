# Phase 6: Band Map & Visualization

**Status**: ✅ Complete
**Date**: 2025-01-13

## Overview

Phase 6 implements **band map visualization** - a graphical representation of band activity showing stations at different frequencies with color-coded status indicators, signal strength, and click-to-tune functionality.

### Key Features

- **Visual frequency spectrum** - Stations plotted on frequency grid
- **Color-coded markers** - Green (NEW), Gold (MULT), Red (WORKED), Gray (unclear)
- **Signal strength indicators** - Visual S-meter bars
- **Click-to-tune** - Click station to tune radio
- **Station detail panel** - Comprehensive station information display
- **Real-time updates** - Band map updates as stations are discovered
- **State management** - Track all stations with metadata

---

## Architecture

### Band Map System

```
BandMapState → Manages station collection
     ↓
BandMapWidget → Visualizes stations on frequency spectrum
     ↓
StationDetailPanel → Shows detailed info for selected station
     ↓
Signals → tune_requested, mark_worked_requested, etc.
```

### Components

1. **BandMapStation** - Data model for individual stations
2. **BandMapState** - State management for station collection
3. **BandMapWidget** - Visual frequency spectrum display
4. **StationDetailPanel** - Detailed information panel

---

## Station Data Model

### BandMapStation Class

Complete representation of a detected station:

```python
@dataclass
class BandMapStation:
    # Core identification
    frequency: float  # Hz
    callsign: Optional[str]
    voice_id: Optional[str]  # UUID from voice database

    # Status
    status: StationStatus  # NEW, WORKED, MULTIPLIER, UNCLEAR
    worked: bool
    is_multiplier: bool

    # Signal quality
    signal_strength: Optional[float]  # S-meter (0-9+)
    snr: Optional[float]  # Signal-to-noise ratio

    # Activity analysis
    contestness_score: float  # 0-100
    activity_type: ActivityType  # RUN_STATION, SEARCH_POUNCE, RAGCHEW
    is_run_station: bool

    # Contest data
    exchange: Optional[str]  # "2A WWA", "Zone 7"
    section: Optional[str]
    zone: Optional[str]

    # Timestamps
    first_heard: datetime
    last_heard: datetime

    # Transcripts
    transcripts: List[str]
    last_transcript: Optional[str]
```

### StationStatus Enum

```python
class StationStatus(Enum):
    NEW = "new"          # Not worked yet
    WORKED = "worked"    # Already worked (dupe)
    MULTIPLIER = "multiplier"  # New multiplier
    UNCLEAR = "unclear"  # Status unknown
```

### ActivityType Enum

```python
class ActivityType(Enum):
    RUN_STATION = "run_station"
    SEARCH_POUNCE = "search_pounce"
    RAGCHEW = "ragchew"
    UNCLEAR = "unclear"
```

---

## Band Map State Management

### BandMapState Class

Manages collection of stations with filtering and sorting:

```python
from cqsentinel.bandmap import BandMapState, BandMapStation, StationStatus

# Create band map state
band_map = BandMapState(band="20m")

# Add or update station
station = band_map.add_or_update_station(
    frequency=14250000,  # 14.250 MHz
    callsign="W1AW",
    status=StationStatus.NEW,
    contestness_score=85.0,
    signal_strength=8.5,
    exchange="2A CT"
)

# Find station by frequency
station = band_map.find_station_by_frequency(14250000, tolerance_hz=1000)

# Find by callsign
station = band_map.find_station_by_callsign("W1AW")

# Get stations sorted
sorted_stations = band_map.get_stations_sorted(sort_by="frequency")

# Get only new stations
new_stations = band_map.get_new_stations()

# Get multipliers
multipliers = band_map.get_multipliers()

# Get recent stations (last 5 minutes)
recent = band_map.get_recent_stations(max_age_minutes=5.0)

# Remove stale stations (>15 minutes old)
removed_count = band_map.remove_stale_stations(max_age_minutes=15.0)

# Statistics
stats = band_map.get_statistics()
print(f"Total: {stats['total_stations']}")
print(f"New: {stats['new_stations']}")
print(f"Worked: {stats['worked_stations']}")
```

---

## Band Map Widget

### BandMapWidget Class

Visual display of stations on frequency spectrum:

**Features:**
- Frequency grid with labels (e.g., 14.000, 14.050, 14.100 MHz)
- Station markers color-coded by status
- Callsign labels
- Signal strength bars
- Click-to-tune functionality
- Selection highlighting

**Color Scheme:**
- **Green**: NEW (unworked stations)
- **Gold**: MULTIPLIER (new multipliers)
- **Red**: WORKED (dupes)
- **Gray**: UNCLEAR (unknown status)

### Usage Example

```python
from PyQt6.QtWidgets import QApplication
from cqsentinel.bandmap import BandMapWidget, BandMapState

app = QApplication([])

# Create band map
band_map = BandMapState(band="20m")
widget = BandMapWidget(band_map)

# Set frequency range for 20m SSB
widget.set_frequency_range(14.000e6, 14.350e6)

# Connect signals
widget.station_clicked.connect(on_station_clicked)
widget.station_selected.connect(on_station_selected)

# Add stations
band_map.add_or_update_station(
    frequency=14250000,
    callsign="W1AW",
    status=StationStatus.NEW,
    signal_strength=8.0
)

# Update display
widget.update_display()

widget.show()
app.exec()
```

### Click-to-Tune

When user clicks a station marker:

```python
def on_station_clicked(frequency_hz):
    """Handle station click - tune radio to frequency."""
    print(f"Tuning to {frequency_hz/1e6:.3f} MHz")
    radio.set_frequency(int(frequency_hz))

def on_station_selected(station):
    """Handle station selection - show details."""
    print(f"Selected: {station.callsign} at {station.frequency_mhz:.3f} MHz")
    detail_panel.set_station(station)
```

---

## Station Detail Panel

### StationDetailPanel Class

Displays comprehensive information about selected station:

**Information Shown:**
- Frequency and band
- Callsign (with emphasis)
- Status (color-coded)
- Signal strength (S-meter + SNR)
- Contestness score (0-100)
- Activity type (run/S&P/ragchew)
- Exchange information
- Estimated QSO rate
- First/last heard times
- Age since last heard
- Recent transcripts (last 3)

**Action Buttons:**
- **Tune To**: Tune radio to station frequency
- **Mark Worked**: Mark station as worked
- **Ignore**: Ignore this station

### Usage Example

```python
from cqsentinel.bandmap import StationDetailPanel

# Create detail panel
detail_panel = StationDetailPanel()

# Connect signals
detail_panel.tune_requested.connect(on_tune_requested)
detail_panel.mark_worked_requested.connect(on_mark_worked)
detail_panel.ignore_requested.connect(on_ignore)

# Set station to display
detail_panel.set_station(station)

# Update display
detail_panel.refresh()
```

---

## Integration Example

### Complete Band Map System

```python
from PyQt6.QtWidgets import QApplication, QMainWindow, QHBoxLayout, QWidget
from cqsentinel.bandmap import (
    BandMapState, BandMapWidget, StationDetailPanel,
    BandMapStation, StationStatus
)
from cqsentinel.radio import HamlibController

class BandMapWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # Create band map state
        self.band_map = BandMapState(band="20m")

        # Create widgets
        self.map_widget = BandMapWidget(self.band_map)
        self.detail_panel = StationDetailPanel()

        # Set frequency range for 20m SSB
        self.map_widget.set_frequency_range(14.000e6, 14.350e6)

        # Connect signals
        self.map_widget.station_clicked.connect(self.on_tune)
        self.map_widget.station_selected.connect(self.on_select)
        self.detail_panel.tune_requested.connect(self.on_tune)
        self.detail_panel.mark_worked_requested.connect(self.on_mark_worked)

        # Layout
        central = QWidget()
        layout = QHBoxLayout()
        layout.addWidget(self.map_widget, stretch=3)
        layout.addWidget(self.detail_panel, stretch=1)
        central.setLayout(layout)
        self.setCentralWidget(central)

        # Radio
        self.radio = HamlibController()

    def on_tune(self, frequency_hz):
        """Tune radio to frequency."""
        self.radio.set_frequency(int(frequency_hz))

    def on_select(self, station):
        """Show station details."""
        self.detail_panel.set_station(station)

    def on_mark_worked(self, station):
        """Mark station as worked."""
        station.worked = True
        station.status = StationStatus.WORKED
        self.map_widget.update_display()
        self.detail_panel.set_station(station)

    def add_detected_station(self, freq, callsign, contestness, signal):
        """Add newly detected station to band map."""
        station = self.band_map.add_or_update_station(
            frequency=freq,
            callsign=callsign,
            status=StationStatus.NEW,
            contestness_score=contestness,
            signal_strength=signal
        )
        self.map_widget.update_display()
        return station

# Run
app = QApplication([])
window = BandMapWindow()
window.show()

# Simulate adding stations
window.add_detected_station(14250000, "W1AW", 85.0, 8.5)
window.add_detected_station(14275000, "K7ABC", 78.0, 7.2)
window.add_detected_station(14300000, "N1MM", 92.0, 9.1)

app.exec()
```

---

## Visual Design

### Band Map Display

```
┌─────────────────────────────────────────────────────────┐
│ Band: 20m          Stations: 12 | New: 8 | Worked: 4   │
├─────────────────────────────────────────────────────────┤
│                                                         │
│              W1AW                K7ABC        N1MM      │
│              ● NEW              ● MULT       ● WORKED   │
│                                                         │
│  ·    ·    ·    ·    ·    ·    ·    ·    ·    ·    ·  │
│  |    |    |    |    |    |    |    |    |    |    |  │
│14.000  .050  .100  .150  .200  .250  .300  .350 MHz   │
└─────────────────────────────────────────────────────────┘
```

### Station Markers

- **Circle size**: 20 pixels diameter
- **Label position**: Callsign above marker, status below
- **Signal bars**: Up to 9 bars showing S-meter reading
- **Selection**: White outline when selected
- **Vertical position**: Higher contestness = higher on display

---

## Files Created

### New Files

1. **cqsentinel/bandmap/station.py** (450 lines)
   - BandMapStation dataclass
   - BandMapState class
   - StationStatus and ActivityType enums
   - Station filtering and sorting

2. **cqsentinel/bandmap/widget.py** (350 lines)
   - BandMapWidget visualization
   - Custom paint event for drawing
   - Frequency grid rendering
   - Station marker drawing
   - Click-to-tune functionality

3. **cqsentinel/bandmap/detail_panel.py** (300 lines)
   - StationDetailPanel widget
   - Comprehensive station info display
   - Action buttons (Tune, Mark Worked, Ignore)
   - Real-time updates

4. **cqsentinel/bandmap/__init__.py**
   - Module exports

---

## Summary

Phase 6 adds **visual band activity representation** to CQSentinel:

✅ **Station data model** - Complete station metadata tracking
✅ **Band map state** - Collection management with filtering/sorting
✅ **Visual display** - Frequency spectrum with color-coded markers
✅ **Click-to-tune** - Direct radio control from band map
✅ **Detail panel** - Comprehensive station information
✅ **Real-time updates** - Dynamic band map as stations discovered
✅ **Color coding** - Green (NEW), Gold (MULT), Red (WORKED), Gray (unclear)
✅ **Signal indicators** - Visual S-meter bars

**Result**: Operators can now **see** band activity at a glance, identify new stations and multipliers visually, and click to tune directly to interesting stations.

**Ready for Phase 7: N3FJP Integration** 📡
