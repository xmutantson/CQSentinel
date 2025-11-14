"""
Callsign extraction and validation.

Extracts amateur radio callsigns from transcripts using multiple approaches:
1. Direct callsign patterns (W1AW, K7ABC, etc.)
2. Phonetic alphabet parsing (kilo seven alpha bravo charlie → K7ABC)
3. Context-aware extraction (after "this is", "de", etc.)
"""

import logging
import re
from typing import List, Optional, Set, Tuple
from dataclasses import dataclass

from cqsentinel.contest.phonetics import PhoneticParser

logger = logging.getLogger(__name__)


# Common callsign prefixes by country/region
# US: K, W, N, A (+ regional numbers 0-9)
# Canada: VA, VE, VO, VY, CF, CG, CH, CJ, CK, CY, CZ, XJ, XK, XL, XM, XN, XO
# Mexico: XE, XF
# Many others...

CALLSIGN_PATTERNS = [
    # Standard format: prefix + digit + suffix
    r'\b([A-Z]{1,2}\d[A-Z]{1,4})\b',          # W1AW, K7ABC, etc.
    r'\b([A-Z]\d[A-Z]{2,3})\b',                # N1MM, K1TTT, etc.

    # With portable/mobile indicators
    r'\b([A-Z]{1,2}\d[A-Z]{1,4})/[A-Z0-9]+\b',  # W1AW/7, K7ABC/M
    r'\b([A-Z]{1,2}\d[A-Z]{1,4})/P\b',          # Portable
    r'\b([A-Z]{1,2}\d[A-Z]{1,4})/M\b',          # Mobile
    r'\b([A-Z]{1,2}\d[A-Z]{1,4})/QRP\b',        # QRP

    # Special event calls
    r'\b(W\d[A-Z]{2,3})\b',                     # Special events
]


# Context patterns that often precede callsigns
CONTEXT_PATTERNS = [
    r'this\s+is\s+([A-Z0-9/]+)',
    r'de\s+([A-Z0-9/]+)',
    r'from\s+([A-Z0-9/]+)',
    r'([A-Z0-9/]+)\s+calling',
    r'([A-Z0-9/]+)\s+here',
    r'cq\s+.*?([A-Z0-9/]+)',
]


@dataclass
class ExtractedCallsign:
    """Represents an extracted callsign with metadata."""
    callsign: str
    confidence: float  # 0-1
    source: str  # 'direct', 'phonetic', 'context'
    position: int  # Character position in text
    is_valid: bool  # Passed validation


class CallsignExtractor:
    """
    Extracts amateur radio callsigns from transcripts.

    Uses multiple strategies:
    1. Direct pattern matching (highest confidence)
    2. Phonetic parsing (medium confidence)
    3. Context-based extraction (varies)

    Usage:
        extractor = CallsignExtractor()
        callsigns = extractor.extract("W1AW kilo seven alpha bravo charlie")
        for cs in callsigns:
            print(f"{cs.callsign} (confidence: {cs.confidence:.2f})")
    """

    def __init__(self, phonetic_parser: Optional[PhoneticParser] = None):
        """
        Initialize callsign extractor.

        Args:
            phonetic_parser: PhoneticParser instance (creates default if None)
        """
        self.phonetic_parser = phonetic_parser or PhoneticParser()
        self.seen_callsigns: Set[str] = set()

        logger.info("CallsignExtractor initialized")

    def extract(
        self,
        text: str,
        min_confidence: float = 0.5
    ) -> List[ExtractedCallsign]:
        """
        Extract callsigns from text.

        Args:
            text: Text to search (transcript)
            min_confidence: Minimum confidence threshold (0-1)

        Returns:
            List of ExtractedCallsign objects sorted by confidence

        Example:
            >>> extractor = CallsignExtractor()
            >>> callsigns = extractor.extract("This is W1AW")
            >>> print(callsigns[0].callsign)
            'W1AW'
        """
        results = []

        # Strategy 1: Direct pattern matching
        results.extend(self._extract_direct(text))

        # Strategy 2: Phonetic parsing
        results.extend(self._extract_phonetic(text))

        # Strategy 3: Context-based
        results.extend(self._extract_context(text))

        # Remove duplicates (keep highest confidence)
        unique_results = self._deduplicate(results)

        # Filter by minimum confidence
        filtered = [cs for cs in unique_results if cs.confidence >= min_confidence]

        # Sort by confidence (descending)
        filtered.sort(key=lambda x: x.confidence, reverse=True)

        logger.debug(f"Extracted {len(filtered)} callsigns from text")

        return filtered

    def extract_best(self, text: str) -> Optional[str]:
        """
        Extract single best callsign from text.

        Args:
            text: Text to search

        Returns:
            Best callsign or None

        Example:
            >>> extractor.extract_best("This is W1AW calling")
            'W1AW'
        """
        results = self.extract(text, min_confidence=0.5)
        return results[0].callsign if results else None

    def _extract_direct(self, text: str) -> List[ExtractedCallsign]:
        """Extract callsigns using direct pattern matching."""
        results = []

        for pattern in CALLSIGN_PATTERNS:
            for match in re.finditer(pattern, text.upper(), re.IGNORECASE):
                callsign = match.group(1) if match.groups() else match.group(0)
                callsign = callsign.upper()

                # Validate format
                is_valid = self._validate_callsign(callsign)

                results.append(ExtractedCallsign(
                    callsign=callsign,
                    confidence=0.95 if is_valid else 0.7,
                    source='direct',
                    position=match.start(),
                    is_valid=is_valid
                ))

        return results

    def _extract_phonetic(self, text: str) -> List[ExtractedCallsign]:
        """Extract callsigns from phonetic sequences."""
        results = []

        # Find phonetic sequences
        sequences = self.phonetic_parser.find_phonetic_sequences(text)

        for seq, start, end in sequences:
            if len(seq) < 3:
                continue  # Too short to be a callsign

            is_valid = self._validate_callsign(seq)

            # Confidence based on length and validity
            confidence = 0.8 if is_valid else 0.5
            if len(seq) >= 4:
                confidence += 0.1

            results.append(ExtractedCallsign(
                callsign=seq,
                confidence=min(confidence, 0.95),
                source='phonetic',
                position=start,
                is_valid=is_valid
            ))

        return results

    def _extract_context(self, text: str) -> List[ExtractedCallsign]:
        """Extract callsigns using context patterns."""
        results = []

        text_upper = text.upper()

        for pattern in CONTEXT_PATTERNS:
            for match in re.finditer(pattern, text_upper, re.IGNORECASE):
                callsign = match.group(1).strip()

                is_valid = self._validate_callsign(callsign)

                # Confidence based on context pattern and validity
                confidence = 0.85 if is_valid else 0.6

                results.append(ExtractedCallsign(
                    callsign=callsign,
                    confidence=confidence,
                    source='context',
                    position=match.start(),
                    is_valid=is_valid
                ))

        return results

    def _validate_callsign(self, callsign: str) -> bool:
        """
        Validate callsign format.

        Args:
            callsign: Callsign to validate

        Returns:
            True if valid format
        """
        if not callsign or len(callsign) < 3:
            return False

        # Remove portable indicators for validation
        base_call = re.sub(r'/[A-Z0-9]+$', '', callsign)

        # Must contain at least one letter and one digit
        has_letter = any(c.isalpha() for c in base_call)
        has_digit = any(c.isdigit() for c in base_call)

        if not (has_letter and has_digit):
            return False

        # Basic pattern: 1-2 letters, digit, 1-4 alphanumeric
        pattern = r'^[A-Z]{1,2}\d[A-Z0-9]{1,4}$'

        return bool(re.match(pattern, base_call))

    def _deduplicate(self, callsigns: List[ExtractedCallsign]) -> List[ExtractedCallsign]:
        """
        Remove duplicate callsigns, keeping highest confidence.

        Args:
            callsigns: List of extracted callsigns

        Returns:
            Deduplicated list
        """
        # Group by callsign
        by_call = {}
        for cs in callsigns:
            if cs.callsign not in by_call:
                by_call[cs.callsign] = cs
            else:
                # Keep higher confidence
                if cs.confidence > by_call[cs.callsign].confidence:
                    by_call[cs.callsign] = cs

        return list(by_call.values())

    def extract_from_transcript_segments(
        self,
        segments: List[dict]
    ) -> List[Tuple[str, float, float]]:
        """
        Extract callsigns from transcript segments with timestamps.

        Args:
            segments: List of transcript segments with 'text', 'start', 'end'

        Returns:
            List of (callsign, start_time, end_time) tuples

        Example:
            >>> segments = [
            ...     {'text': 'This is W1AW', 'start': 0.0, 'end': 2.5},
            ...     {'text': 'kilo seven alpha bravo charlie', 'start': 3.0, 'end': 6.0}
            ... ]
            >>> extractor.extract_from_transcript_segments(segments)
            [('W1AW', 0.0, 2.5), ('K7ABC', 3.0, 6.0)]
        """
        results = []

        for segment in segments:
            text = segment.get('text', '')
            start = segment.get('start', 0.0)
            end = segment.get('end', 0.0)

            callsigns = self.extract(text, min_confidence=0.6)

            for cs in callsigns:
                results.append((cs.callsign, start, end))

        return results

    def get_unique_callsigns(self, text: str) -> List[str]:
        """
        Get list of unique callsigns from text.

        Args:
            text: Text to search

        Returns:
            List of unique callsigns sorted by confidence

        Example:
            >>> extractor.get_unique_callsigns("W1AW calling K7ABC, K7ABC come back")
            ['W1AW', 'K7ABC']
        """
        extracted = self.extract(text, min_confidence=0.6)
        seen = set()
        unique = []

        for cs in extracted:
            if cs.callsign not in seen:
                seen.add(cs.callsign)
                unique.append(cs.callsign)

        return unique

    def is_likely_callsign(self, text: str) -> bool:
        """
        Quick check if text likely contains a callsign.

        Args:
            text: Text to check

        Returns:
            True if callsign likely present
        """
        # Quick pattern check
        pattern = r'\b[A-Z]{1,2}\d[A-Z0-9]{1,4}\b'
        return bool(re.search(pattern, text.upper()))


# Singleton instance
_default_extractor = None


def get_extractor() -> CallsignExtractor:
    """Get default callsign extractor instance."""
    global _default_extractor
    if _default_extractor is None:
        _default_extractor = CallsignExtractor()
    return _default_extractor


def extract_callsigns(text: str, min_confidence: float = 0.6) -> List[str]:
    """
    Convenience function to extract callsigns from text.

    Args:
        text: Text to search
        min_confidence: Minimum confidence threshold

    Returns:
        List of callsigns

    Example:
        >>> extract_callsigns("This is W1AW calling K7ABC")
        ['W1AW', 'K7ABC']
    """
    extractor = get_extractor()
    results = extractor.extract(text, min_confidence=min_confidence)
    return [cs.callsign for cs in results]


def extract_best_callsign(text: str) -> Optional[str]:
    """
    Convenience function to extract best callsign from text.

    Args:
        text: Text to search

    Returns:
        Best callsign or None
    """
    return get_extractor().extract_best(text)
