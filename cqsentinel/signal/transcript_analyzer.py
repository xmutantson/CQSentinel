"""
Transcript Analysis for Contest Detection and Callsign Extraction

Analyzes Whisper transcripts to determine if activity is a contest
and identify the running station's callsign.
"""

import re
import logging
from typing import Optional, Tuple, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# Contest indicator keywords (normalized to lowercase for matching)
CONTEST_KEYWORDS = {
    # Direct contest mentions
    "contest", "cq contest", "calling cq", "cq cq",
    # Common exchanges
    "five nine", "five seven", "five five", "59", "57", "55",
    "your 59", "you're 59", "you are 59",
    # Contest mechanics
    "qsl", "roger", "good luck", "73", "thanks", "thank you",
    "go ahead", "again please", "say again",
    # Sweepstakes specific
    "precedence", "check", "section",
    "alpha", "bravo", "charlie", "delta", "echo", "one alpha", "two alpha",
    # Field Day
    "field day", "one bravo", "two echo", "three foxtrot",
    "home station", "battery power", "emergency power",
    # Serial numbers
    "serial", "number", "zero zero one", "zero zero two",
    # Contest names
    "sweepstakes", "arrl", "wpx", "cqww", "cq world wide",
    "winter field day", "ss", "fd",
    # Phonetics (indicates callsign exchange)
    "whiskey", "november", "kilo", "alpha", "bravo", "charlie",
    "delta", "echo", "foxtrot", "golf", "hotel", "india",
    "juliet", "lima", "mike", "oscar", "papa", "quebec",
    "romeo", "sierra", "tango", "uniform", "victor",
    "x-ray", "xray", "yankee", "zulu",
}

# Non-contest indicators (casual QSO, rag chew)
NON_CONTEST_KEYWORDS = {
    "weather", "temperature", "degrees", "raining", "sunny",
    "antenna", "rig", "watt", "equipment",
    "name is", "my name", "first name",
    "qth is", "located in", "location",
    "been licensed", "years old", "family",
    "back to you for any comments",
}


@dataclass
class ContestAnalysis:
    """Results of contest transcript analysis"""
    is_contest: bool = False
    confidence: float = 0.0  # 0.0 to 1.0
    running_station_callsign: Optional[str] = None
    detected_keywords: List[str] = None
    contest_type: Optional[str] = None  # Sweepstakes, Field Day, etc.

    def __post_init__(self):
        if self.detected_keywords is None:
            self.detected_keywords = []


class TranscriptAnalyzer:
    """
    Analyzes transcripts to detect contests and extract callsigns.
    """

    def __init__(self):
        """Initialize transcript analyzer."""
        # Compile regex patterns for callsign extraction
        # Matches patterns like W7WA, N3ABC, KG7ABC, AA5XY, VE3ABC
        self.callsign_pattern = re.compile(
            r'\b([AKNWV][A-Z]?\d[A-Z]{1,3})\b',
            re.IGNORECASE
        )

        # NATO phonetic to letter mapping
        self.phonetic_to_letter = {
            'alpha': 'A', 'bravo': 'B', 'charlie': 'C', 'delta': 'D',
            'echo': 'E', 'foxtrot': 'F', 'golf': 'G', 'hotel': 'H',
            'india': 'I', 'juliet': 'J', 'kilo': 'K', 'lima': 'L',
            'mike': 'M', 'november': 'N', 'oscar': 'O', 'papa': 'P',
            'quebec': 'Q', 'romeo': 'R', 'sierra': 'S', 'tango': 'T',
            'uniform': 'U', 'victor': 'V', 'whiskey': 'W', 'x-ray': 'X',
            'xray': 'X', 'yankee': 'Y', 'zulu': 'Z',
            # Numbers
            'zero': '0', 'one': '1', 'two': '2', 'three': '3',
            'four': '4', 'five': '5', 'six': '6', 'seven': '7',
            'eight': '8', 'nine': '9', 'niner': '9',
        }

        logger.info("TranscriptAnalyzer initialized")

    def analyze_contest(self, transcript: str) -> ContestAnalysis:
        """
        Analyze transcript for contest activity.

        Args:
            transcript: Full transcript text (e.g., 90 seconds of audio)

        Returns:
            ContestAnalysis with detection results
        """
        result = ContestAnalysis()

        if not transcript or not transcript.strip():
            return result

        text_lower = transcript.lower()

        # Count contest keyword matches
        contest_matches = []
        for keyword in CONTEST_KEYWORDS:
            if keyword in text_lower:
                contest_matches.append(keyword)

        # Count non-contest keyword matches
        non_contest_matches = []
        for keyword in NON_CONTEST_KEYWORDS:
            if keyword in text_lower:
                non_contest_matches.append(keyword)

        result.detected_keywords = contest_matches

        # Calculate confidence based on keyword density
        # More contest keywords = higher confidence
        # More non-contest keywords = lower confidence
        contest_score = len(contest_matches)
        non_contest_score = len(non_contest_matches)

        # Boost score for strong indicators
        if "cq contest" in text_lower or "contest" in text_lower:
            contest_score += 5
        if any(x in text_lower for x in ["five nine", "59", "five seven", "57"]):
            contest_score += 3
        if any(x in text_lower for x in ["field day", "sweepstakes", "arrl"]):
            contest_score += 4

        # Penalize for non-contest indicators
        total_score = contest_score - (non_contest_score * 2)

        # Convert to confidence (0-1)
        if total_score <= 0:
            result.confidence = 0.0
            result.is_contest = False
        elif total_score < 3:
            result.confidence = 0.3
            result.is_contest = False
        elif total_score < 6:
            result.confidence = 0.5
            result.is_contest = True  # Borderline, but probably contest
        elif total_score < 10:
            result.confidence = 0.7
            result.is_contest = True
        else:
            result.confidence = 0.9
            result.is_contest = True

        # Detect contest type
        result.contest_type = self._detect_contest_type(text_lower)

        # Extract running station callsign
        result.running_station_callsign = self.extract_running_station(transcript)

        logger.info(
            f"Contest analysis: is_contest={result.is_contest}, "
            f"confidence={result.confidence:.2f}, "
            f"callsign={result.running_station_callsign}, "
            f"type={result.contest_type}, "
            f"keywords={len(contest_matches)}"
        )

        return result

    def _detect_contest_type(self, text_lower: str) -> Optional[str]:
        """Detect specific contest type from transcript."""
        if "field day" in text_lower or any(
            x in text_lower for x in ["one bravo", "two echo", "three foxtrot", "one alpha"]
        ):
            return "Field Day"
        elif "sweepstakes" in text_lower or "precedence" in text_lower or "check" in text_lower:
            return "ARRL Sweepstakes"
        elif "wpx" in text_lower:
            return "CQ WPX"
        elif "cqww" in text_lower or "cq world wide" in text_lower:
            return "CQ World Wide"
        elif "winter field day" in text_lower:
            return "Winter Field Day"
        elif "arrl" in text_lower:
            return "ARRL Contest"
        else:
            return "Unknown Contest"

    def extract_running_station(self, transcript: str) -> Optional[str]:
        """
        Extract the running station's callsign from transcript.

        The running station is typically:
        1. The one calling CQ
        2. The one that appears most frequently
        3. The one giving their callsign after "this is"

        Args:
            transcript: Full transcript text

        Returns:
            Callsign of running station, or None if not found
        """
        text_lower = transcript.lower()

        # Strategy 1: Look for "CQ ... <callsign>"
        callsign_after_cq = self._extract_after_cq(transcript)
        if callsign_after_cq:
            logger.debug(f"Found callsign after CQ: {callsign_after_cq}")
            return callsign_after_cq

        # Strategy 2: Look for "this is <callsign>"
        callsign_after_this_is = self._extract_after_this_is(transcript)
        if callsign_after_this_is:
            logger.debug(f"Found callsign after 'this is': {callsign_after_this_is}")
            return callsign_after_this_is

        # Strategy 3: Most frequently mentioned callsign
        all_callsigns = self._extract_all_callsigns(transcript)
        if all_callsigns:
            # Count occurrences
            from collections import Counter
            counts = Counter(all_callsigns)
            most_common = counts.most_common(1)[0][0]
            logger.debug(f"Most common callsign: {most_common} (appears {counts[most_common]} times)")
            return most_common

        # Strategy 4: Try to reconstruct from phonetics
        phonetic_callsign = self._extract_from_phonetics(transcript)
        if phonetic_callsign:
            logger.debug(f"Reconstructed callsign from phonetics: {phonetic_callsign}")
            return phonetic_callsign

        logger.debug("No callsign found in transcript")
        return None

    def _extract_after_cq(self, transcript: str) -> Optional[str]:
        """Extract callsign that appears after CQ."""
        # Look for patterns like "CQ contest W7WA" or "CQ CQ W7WA"
        text_upper = transcript.upper()

        # Find CQ followed by optional words then callsign
        cq_pattern = re.compile(
            r'CQ(?:\s+(?:CONTEST|CQ|DX))?\s+([AKNWV][A-Z]?\d[A-Z]{1,3})',
            re.IGNORECASE
        )

        match = cq_pattern.search(text_upper)
        if match:
            return match.group(1).upper()

        return None

    def _extract_after_this_is(self, transcript: str) -> Optional[str]:
        """Extract callsign that appears after 'this is'."""
        text_upper = transcript.upper()

        # Pattern: "this is <callsign>"
        this_is_pattern = re.compile(
            r'THIS\s+IS\s+([AKNWV][A-Z]?\d[A-Z]{1,3})',
            re.IGNORECASE
        )

        match = this_is_pattern.search(text_upper)
        if match:
            return match.group(1).upper()

        return None

    def _extract_all_callsigns(self, transcript: str) -> List[str]:
        """Extract all callsign-like patterns from transcript."""
        matches = self.callsign_pattern.findall(transcript)
        # Normalize to uppercase
        return [m.upper() for m in matches]

    def _extract_from_phonetics(self, transcript: str) -> Optional[str]:
        """
        Try to reconstruct callsign from phonetic spelling.

        E.g., "Whiskey Seven Whiskey Alpha" -> "W7WA"
        """
        text_lower = transcript.lower()
        words = text_lower.split()

        # Look for sequences that could be a callsign
        # Callsigns are typically 4-6 characters: prefix (1-2 letters), number (1), suffix (1-3 letters)

        callsign_chars = []
        building_callsign = False

        for word in words:
            if word in self.phonetic_to_letter:
                char = self.phonetic_to_letter[word]
                callsign_chars.append(char)
                building_callsign = True

                # Check if we have a valid callsign pattern
                current = ''.join(callsign_chars)
                if len(current) >= 4 and self._is_valid_callsign(current):
                    return current
            else:
                # Reset if we hit a non-phonetic word and have a valid callsign
                if building_callsign and len(callsign_chars) >= 4:
                    current = ''.join(callsign_chars)
                    if self._is_valid_callsign(current):
                        return current

                # Reset if hit break word
                if building_callsign and word not in ['and', 'is', 'at', 'the']:
                    callsign_chars = []
                    building_callsign = False

        # Check final accumulated chars
        if callsign_chars and len(callsign_chars) >= 4:
            current = ''.join(callsign_chars)
            if self._is_valid_callsign(current):
                return current

        return None

    def _is_valid_callsign(self, callsign: str) -> bool:
        """
        Check if string matches valid amateur callsign pattern.

        Valid US patterns: W7WA, N3ABC, KG7XYZ, AA5GH
        Valid VE patterns: VE3ABC, VA7XYZ
        """
        if len(callsign) < 4 or len(callsign) > 7:
            return False

        # Must start with A, K, N, W, or V (US/Canada)
        if callsign[0] not in 'AKNWV':
            return False

        # Must contain at least one digit
        if not any(c.isdigit() for c in callsign):
            return False

        # Check structure: letters, then digit(s), then letters
        has_digit = False
        post_digit_letters = 0

        for i, c in enumerate(callsign):
            if c.isdigit():
                has_digit = True
            elif has_digit:
                post_digit_letters += 1

        # Must have 1-3 letters after the number
        return 1 <= post_digit_letters <= 3
