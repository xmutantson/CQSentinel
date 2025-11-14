"""
Contest behavior detection and classification.

Analyzes transcripts and voice data to:
1. Calculate "contestness" score (0-100)
2. Classify station type (run, S&P, ragchew)
3. Detect contest activity patterns
"""

import logging
import re
from typing import List, Dict, Optional
from dataclasses import dataclass
from enum import Enum

from cqsentinel.contest.callsign import CallsignExtractor
from cqsentinel.contest.phonetics import PhoneticParser

logger = logging.getLogger(__name__)


class StationType(Enum):
    """Station operating type."""
    RUN_STATION = "run_station"  # Running a frequency
    SEARCH_POUNCE = "search_pounce"  # S&P / hunting
    RAGCHEW = "ragchew"  # Non-contest conversation
    UNCLEAR = "unclear"  # Cannot determine


# Contest keywords and phrases
CONTEST_KEYWORDS = [
    'cq', 'test', 'contest', 'qrz', 'field day', 'winter field day',
    'cqww', 'cq ww', 'wpx', 'salmon run',
    'copy', 'qsl', 'roger', '73', 'thanks for the',
    'you are', 'you\'re', 'sending', 'report',
]


CQ_PHRASES = [
    'cq test', 'cq contest', 'cq field day', 'cq ww', 'cq wpx',
    'cq cq', 'calling cq',
]


# Exchange patterns
EXCHANGE_PATTERNS = [
    r'\b5[79]9?\b',  # RST report
    r'\b\d+[A-F]\b',  # Field Day class (1A, 2A, etc.)
    r'\b[A-Z]{2,3}\b',  # Section/state abbreviation
    r'\bzone\s+\d+\b',  # CQ Zone
]


@dataclass
class ContestnessAnalysis:
    """Results of contestness analysis."""
    score: float  # 0-100
    station_type: StationType
    is_run_station: bool

    # Contributing factors
    keyword_score: float  # 0-20
    callsign_density_score: float  # 0-25
    dominance_score: float  # 0-20
    qso_rate_score: float  # 0-20
    exchange_score: float  # 0-15

    # Metadata
    unique_callsigns: int
    callsigns_per_minute: float
    dominant_speaker_ratio: float


class BehaviorAnalyzer:
    """
    Analyzes contest behavior from transcripts and voice data.

    Calculates contestness score and classifies station type based on:
    - Contest keyword frequency
    - Callsign density
    - Speaker dominance patterns
    - QSO rate
    - Exchange pattern detection

    Usage:
        analyzer = BehaviorAnalyzer()
        result = analyzer.analyze(
            transcript_text="CQ Field Day W1AW...",
            duration=60.0,
            voice_segments=[...]
        )
        print(f"Contestness: {result.score}/100")
        print(f"Type: {result.station_type.value}")
    """

    def __init__(
        self,
        callsign_extractor: Optional[CallsignExtractor] = None
    ):
        """
        Initialize behavior analyzer.

        Args:
            callsign_extractor: CallsignExtractor instance
        """
        self.callsign_extractor = callsign_extractor or CallsignExtractor()

        logger.info("BehaviorAnalyzer initialized")

    def analyze(
        self,
        transcript_text: str,
        duration: float,
        voice_segments: Optional[List[dict]] = None,
        transcript_segments: Optional[List[dict]] = None
    ) -> ContestnessAnalysis:
        """
        Analyze contest behavior from audio/transcript data.

        Args:
            transcript_text: Full transcript text
            duration: Duration in seconds
            voice_segments: Voice fingerprint segments with speaker IDs
            transcript_segments: Transcript segments with timestamps

        Returns:
            ContestnessAnalysis with score and classification

        Example:
            >>> analyzer = BehaviorAnalyzer()
            >>> result = analyzer.analyze(
            ...     "CQ Field Day W1AW W1AW",
            ...     duration=60.0
            ... )
            >>> print(result.score)
            75.2
        """
        full_text = transcript_text.lower()

        # 1. Keyword Detection (0-20 points)
        keyword_score = self._calculate_keyword_score(full_text)

        # 2. Callsign Density (0-25 points)
        callsigns = self.callsign_extractor.get_unique_callsigns(transcript_text)
        callsign_density_score, callsigns_per_min = self._calculate_callsign_density_score(
            callsigns,
            duration
        )

        # 3. Speaker Dominance (0-20 points)
        dominance_score, dominant_ratio = self._calculate_dominance_score(
            voice_segments,
            duration
        )

        # 4. QSO Rate (0-20 points)
        qso_rate_score = self._calculate_qso_rate_score(
            voice_segments,
            duration
        )

        # 5. Exchange Pattern (0-15 points)
        exchange_score = self._calculate_exchange_score(full_text)

        # Total score
        total_score = (
            keyword_score +
            callsign_density_score +
            dominance_score +
            qso_rate_score +
            exchange_score
        )
        total_score = min(total_score, 100.0)

        # Classify station type
        station_type, is_run = self._classify_station_type(
            total_score,
            dominant_ratio,
            voice_segments
        )

        return ContestnessAnalysis(
            score=total_score,
            station_type=station_type,
            is_run_station=is_run,
            keyword_score=keyword_score,
            callsign_density_score=callsign_density_score,
            dominance_score=dominance_score,
            qso_rate_score=qso_rate_score,
            exchange_score=exchange_score,
            unique_callsigns=len(callsigns),
            callsigns_per_minute=callsigns_per_min,
            dominant_speaker_ratio=dominant_ratio
        )

    def _calculate_keyword_score(self, text: str) -> float:
        """
        Calculate keyword score (0-20 points).

        Args:
            text: Transcript text (lowercase)

        Returns:
            Score 0-20
        """
        hit_count = sum(1 for kw in CONTEST_KEYWORDS if kw in text)

        # Also check for CQ phrases (higher weight)
        cq_hit = any(phrase in text for phrase in CQ_PHRASES)
        if cq_hit:
            hit_count += 2  # Bonus for CQ

        # Normalize to 0-20
        score = min((hit_count / len(CONTEST_KEYWORDS)) * 20, 20.0)

        logger.debug(f"Keyword score: {score:.1f} ({hit_count} hits)")

        return score

    def _calculate_callsign_density_score(
        self,
        callsigns: List[str],
        duration: float
    ) -> tuple[float, float]:
        """
        Calculate callsign density score (0-25 points).

        Args:
            callsigns: List of unique callsigns
            duration: Duration in seconds

        Returns:
            Tuple of (score, callsigns_per_minute)
        """
        if duration == 0:
            return 0.0, 0.0

        # Callsigns per minute
        minutes = duration / 60.0
        density = len(callsigns) / minutes

        # Contest typically has 5-20 callsigns per minute
        # S&P might have 2-5, ragchew < 2
        if density >= 15:
            score = 25.0
        elif density >= 10:
            score = 20.0
        elif density >= 5:
            score = 15.0
        elif density >= 2:
            score = 10.0
        else:
            score = density * 5  # Linear below 2

        score = min(score, 25.0)

        logger.debug(f"Callsign density score: {score:.1f} ({density:.1f} calls/min)")

        return score, density

    def _calculate_dominance_score(
        self,
        voice_segments: Optional[List[dict]],
        duration: float
    ) -> tuple[float, float]:
        """
        Calculate speaker dominance score (0-20 points).

        Run stations typically have one dominant speaker (>60% airtime).

        Args:
            voice_segments: Voice fingerprint segments
            duration: Total duration in seconds

        Returns:
            Tuple of (score, dominant_speaker_ratio)
        """
        if not voice_segments or duration == 0:
            return 0.0, 0.0

        # Calculate airtime per speaker
        speaker_times = {}
        for segment in voice_segments:
            # Assuming segment has 'speaker_id', 'start_time', 'end_time'
            speaker_id = segment.get('speaker_id', 0)
            start = segment.get('start_time', 0.0)
            end = segment.get('end_time', 0.0)
            airtime = end - start

            speaker_times[speaker_id] = speaker_times.get(speaker_id, 0) + airtime

        if not speaker_times:
            return 0.0, 0.0

        # Find dominant speaker ratio
        max_airtime = max(speaker_times.values())
        dominance_ratio = max_airtime / duration
        unique_speakers = len(speaker_times)

        # Scoring:
        # High dominance (>60%) + multiple speakers = run station
        # Low dominance (<40%) = S&P or ragchew
        score = 0.0

        if dominance_ratio > 0.7 and unique_speakers >= 3:
            score = 20.0  # Clear run station
        elif dominance_ratio > 0.6 and unique_speakers >= 2:
            score = 15.0  # Likely run station
        elif dominance_ratio > 0.5:
            score = 10.0  # Moderate dominance
        elif dominance_ratio > 0.4:
            score = 5.0   # Low dominance

        logger.debug(
            f"Dominance score: {score:.1f} "
            f"(ratio: {dominance_ratio:.2f}, speakers: {unique_speakers})"
        )

        return score, dominance_ratio

    def _calculate_qso_rate_score(
        self,
        voice_segments: Optional[List[dict]],
        duration: float
    ) -> float:
        """
        Calculate QSO rate score (0-20 points).

        Args:
            voice_segments: Voice fingerprint segments
            duration: Duration in seconds

        Returns:
            Score 0-20
        """
        if not voice_segments or duration == 0:
            return 0.0

        # Count unique speakers (excluding run station)
        unique_speakers = len(set(
            seg.get('speaker_id', 0) for seg in voice_segments
        ))

        # Estimate QSOs (unique speakers - 1 for run station)
        estimated_qsos = max(unique_speakers - 1, 0)

        # QSOs per minute
        minutes = duration / 60.0
        qso_rate = estimated_qsos / minutes

        # Contest rates: 30-60+ QSOs/hour = 0.5-1.0+ QSOs/minute
        if qso_rate >= 1.0:
            score = 20.0
        elif qso_rate >= 0.5:
            score = 15.0
        elif qso_rate >= 0.25:
            score = 10.0
        elif qso_rate > 0:
            score = qso_rate * 20  # Linear scaling
        else:
            score = 0.0

        score = min(score, 20.0)

        logger.debug(
            f"QSO rate score: {score:.1f} "
            f"({qso_rate:.2f} QSOs/min, {unique_speakers} speakers)"
        )

        return score

    def _calculate_exchange_score(self, text: str) -> float:
        """
        Calculate exchange pattern score (0-15 points).

        Args:
            text: Transcript text (lowercase)

        Returns:
            Score 0-15
        """
        matches = 0

        for pattern in EXCHANGE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                matches += 1

        # Normalize to 0-15
        score = min((matches / len(EXCHANGE_PATTERNS)) * 15, 15.0)

        logger.debug(f"Exchange score: {score:.1f} ({matches} pattern matches)")

        return score

    def _classify_station_type(
        self,
        contestness_score: float,
        dominance_ratio: float,
        voice_segments: Optional[List[dict]]
    ) -> tuple[StationType, bool]:
        """
        Classify station type based on analysis.

        Args:
            contestness_score: Total contestness score (0-100)
            dominance_ratio: Dominant speaker ratio (0-1)
            voice_segments: Voice fingerprint segments

        Returns:
            Tuple of (StationType, is_run_station)
        """
        # Low contestness = ragchew
        if contestness_score < 40:
            return StationType.RAGCHEW, False

        # Count unique speakers
        unique_speakers = 0
        if voice_segments:
            unique_speakers = len(set(
                seg.get('speaker_id', 0) for seg in voice_segments
            ))

        # High dominance + multiple speakers = run station
        if dominance_ratio > 0.6 and unique_speakers >= 3:
            return StationType.RUN_STATION, True

        # Few speakers + high contestness = S&P
        if unique_speakers <= 2 and contestness_score > 60:
            return StationType.SEARCH_POUNCE, False

        # Multiple speakers but low dominance = unclear
        if unique_speakers >= 3 and dominance_ratio < 0.5:
            return StationType.UNCLEAR, False

        # Default to unclear
        return StationType.UNCLEAR, False

    def is_contest_activity(self, contestness_score: float, threshold: float = 70.0) -> bool:
        """
        Quick check if activity is likely contest-related.

        Args:
            contestness_score: Contestness score (0-100)
            threshold: Minimum score to consider contest (default: 70)

        Returns:
            True if likely contest activity
        """
        return contestness_score >= threshold


# Singleton instance
_default_analyzer = None


def get_analyzer() -> BehaviorAnalyzer:
    """Get default behavior analyzer instance."""
    global _default_analyzer
    if _default_analyzer is None:
        _default_analyzer = BehaviorAnalyzer()
    return _default_analyzer


def analyze_contestness(
    transcript: str,
    duration: float,
    voice_segments: Optional[List[dict]] = None
) -> float:
    """
    Convenience function to calculate contestness score.

    Args:
        transcript: Transcript text
        duration: Duration in seconds
        voice_segments: Optional voice fingerprint segments

    Returns:
        Contestness score (0-100)

    Example:
        >>> score = analyze_contestness("CQ Field Day W1AW", duration=60.0)
        >>> print(f"Contestness: {score:.1f}")
    """
    analyzer = get_analyzer()
    result = analyzer.analyze(transcript, duration, voice_segments)
    return result.score
