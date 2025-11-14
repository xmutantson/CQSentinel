"""
Band map and visualization module.

Provides visual representation of band activity with:
- Station data models
- Band map state management
- Frequency spectrum visualization
- Color-coded station markers
- Click-to-tune functionality
- Station detail panel
"""

from cqsentinel.bandmap.station import (
    BandMapStation,
    BandMapState,
    StationStatus,
    ActivityType
)
from cqsentinel.bandmap.widget import BandMapWidget
from cqsentinel.bandmap.detail_panel import StationDetailPanel

__all__ = [
    'BandMapStation',
    'BandMapState',
    'StationStatus',
    'ActivityType',
    'BandMapWidget',
    'StationDetailPanel',
]
