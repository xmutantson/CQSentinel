"""
Phonetic alphabet parsing for amateur radio.

Handles NATO phonetics and creative variations commonly used
in amateur radio contests and general operation.
"""

import logging
import re
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# Standard NATO phonetic alphabet
NATO_PHONETICS = {
    'alpha': 'A',
    'bravo': 'B',
    'charlie': 'C',
    'delta': 'D',
    'echo': 'E',
    'foxtrot': 'F',
    'golf': 'G',
    'hotel': 'H',
    'india': 'I',
    'juliet': 'J',
    'juliett': 'J',  # Alternative spelling
    'kilo': 'K',
    'lima': 'L',
    'mike': 'M',
    'november': 'N',
    'oscar': 'O',
    'papa': 'P',
    'quebec': 'Q',
    'romeo': 'R',
    'sierra': 'S',
    'tango': 'T',
    'uniform': 'U',
    'victor': 'V',
    'whiskey': 'W',
    'xray': 'X',
    'x-ray': 'X',
    'x ray': 'X',
    'yankee': 'Y',
    'zulu': 'Z',
}


# Creative/alternative phonetics commonly used
CREATIVE_PHONETICS = {
    # Common alternatives
    'america': 'A',
    'argentina': 'A',
    'australia': 'A',
    'alaska': 'A',
    'arizona': 'A',

    'boston': 'B',
    'brazil': 'B',
    'baltimore': 'B',

    'california': 'C',
    'canada': 'C',
    'chicago': 'C',
    'china': 'C',

    'denmark': 'D',
    'david': 'D',

    'england': 'E',
    'europe': 'E',
    'ecuador': 'E',

    'florida': 'F',
    'france': 'F',
    'frank': 'F',

    'germany': 'G',
    'guatemala': 'G',
    'george': 'G',

    'hawaii': 'H',
    'henry': 'H',
    'honolulu': 'H',

    'italy': 'I',
    'idaho': 'I',
    'iowa': 'I',

    'japan': 'J',
    'john': 'J',

    'kilowatt': 'K',  # Common in ham radio
    'kentucky': 'K',

    'london': 'L',
    'liberty': 'L',

    'mexico': 'M',
    'mary': 'M',
    'michigan': 'M',

    'norway': 'N',
    'nancy': 'N',
    'new york': 'N',

    'ocean': 'O',  # Common alternative
    'ontario': 'O',
    'oregon': 'O',

    'portugal': 'P',
    'peter': 'P',

    'queen': 'Q',

    'radio': 'R',
    'roger': 'R',
    'robert': 'R',

    'santiago': 'S',
    'spain': 'S',
    'sugar': 'S',
    'sam': 'S',

    'texas': 'T',
    'tokyo': 'T',
    'tom': 'T',

    'united states': 'U',
    'union': 'U',
    'uncle': 'U',

    'venezuela': 'V',
    'victoria': 'V',

    'washington': 'W',
    'william': 'W',
    'watt': 'W',  # Ham radio specific

    'yellow': 'Y',

    'zanzibar': 'Z',
    'zero': 'Z',  # Sometimes used
}


# Number phonetics
NUMBER_WORDS = {
    'zero': '0',
    'one': '1',
    'two': '2',
    'three': '3',
    'four': '4',
    'five': '5',
    'six': '6',
    'seven': '7',
    'eight': '8',
    'nine': '9',
    'niner': '9',  # Aviation/military
    'tree': '3',  # Common pronunciation
    'fower': '4',  # Common pronunciation
    'fife': '5',  # Common pronunciation
}


class PhoneticParser:
    """
    Parser for converting phonetic alphabet to callsigns and exchanges.

    Handles both NATO standard and creative variations commonly used
    in amateur radio.

    Usage:
        parser = PhoneticParser()
        callsign = parser.parse_callsign("kilo seven alpha bravo charlie")
        # Returns: "K7ABC"

        # Add custom phonetics
        parser.add_custom_phonetics({'kilowatt': 'K', 'ocean': 'O'})
    """

    def __init__(self, custom_phonetics: Optional[Dict[str, str]] = None):
        """
        Initialize phonetic parser.

        Args:
            custom_phonetics: Additional custom phonetic mappings
        """
        # Combine all phonetic mappings
        self.phonetics = {}
        self.phonetics.update(NATO_PHONETICS)
        self.phonetics.update(CREATIVE_PHONETICS)

        if custom_phonetics:
            self.phonetics.update({k.lower(): v.upper() for k, v in custom_phonetics.items()})

        self.numbers = NUMBER_WORDS.copy()

        logger.info(f"PhoneticParser initialized ({len(self.phonetics)} phonetics, {len(self.numbers)} numbers)")

    def add_custom_phonetics(self, phonetics: Dict[str, str]):
        """
        Add custom phonetic mappings.

        Args:
            phonetics: Dict mapping phonetic word to letter
        """
        self.phonetics.update({k.lower(): v.upper() for k, v in phonetics.items()})
        logger.info(f"Added {len(phonetics)} custom phonetics")

    def parse_callsign(self, text: str, strict: bool = False) -> Optional[str]:
        """
        Extract callsign from phonetic text.

        Args:
            text: Text containing phonetic callsign
            strict: If True, only accept valid callsign format

        Returns:
            Callsign string or None if not found

        Example:
            >>> parser = PhoneticParser()
            >>> parser.parse_callsign("kilo seven alpha bravo charlie")
            'K7ABC'
            >>> parser.parse_callsign("whiskey one alpha whiskey")
            'W1AW'
        """
        text = text.lower().strip()

        # Split into words
        words = re.split(r'[\s\-,]+', text)

        # Convert phonetics and numbers to characters
        characters = []
        for word in words:
            word = word.strip()
            if not word:
                continue

            # Try phonetic letter
            if word in self.phonetics:
                characters.append(self.phonetics[word])
            # Try number
            elif word in self.numbers:
                characters.append(self.numbers[word])
            # Try direct single character
            elif len(word) == 1 and word.isalnum():
                characters.append(word.upper())
            # Try digit
            elif word.isdigit():
                characters.extend(list(word))

        if not characters:
            return None

        callsign = ''.join(characters)

        # Validate callsign format if strict
        if strict and not self._is_valid_callsign_format(callsign):
            logger.debug(f"Invalid callsign format: {callsign}")
            return None

        return callsign

    def parse_exchange(self, text: str) -> List[str]:
        """
        Extract exchange elements from phonetic text.

        Args:
            text: Text containing phonetic exchange

        Returns:
            List of exchange elements

        Example:
            >>> parser.parse_callsign("five nine two alpha washington")
            ['59', '2A', 'WA']
        """
        text = text.lower().strip()
        words = re.split(r'[\s\-,]+', text)

        elements = []
        current_element = []

        for word in words:
            word = word.strip()
            if not word:
                continue

            # Check for phonetic letter
            if word in self.phonetics:
                current_element.append(self.phonetics[word])
            # Check for number
            elif word in self.numbers:
                current_element.append(self.numbers[word])
            # Check for direct digit
            elif word.isdigit():
                current_element.extend(list(word))
            # Check for single character
            elif len(word) == 1 and word.isalnum():
                current_element.append(word.upper())
            else:
                # Unknown word, might be separator
                if current_element:
                    elements.append(''.join(current_element))
                    current_element = []

        # Add final element
        if current_element:
            elements.append(''.join(current_element))

        return elements

    def find_phonetic_sequences(self, text: str) -> List[Tuple[str, int, int]]:
        """
        Find all phonetic letter/number sequences in text.

        Args:
            text: Text to search

        Returns:
            List of (sequence, start_pos, end_pos) tuples

        Example:
            >>> parser.find_phonetic_sequences("CQ kilo seven alpha bravo charlie")
            [('K7ABC', 3, 33)]
        """
        text_lower = text.lower()
        words = text_lower.split()

        sequences = []
        current_seq = []
        start_idx = 0

        for i, word in enumerate(words):
            is_phonetic = word in self.phonetics or word in self.numbers or (word.isdigit() and len(word) == 1)

            if is_phonetic:
                if not current_seq:
                    # Start new sequence
                    start_idx = i

                # Add to current sequence
                if word in self.phonetics:
                    current_seq.append(self.phonetics[word])
                elif word in self.numbers:
                    current_seq.append(self.numbers[word])
                elif word.isdigit():
                    current_seq.extend(list(word))
            else:
                # End of sequence
                if current_seq:
                    sequences.append((''.join(current_seq), start_idx, i))
                    current_seq = []

        # Add final sequence
        if current_seq:
            sequences.append((''.join(current_seq), start_idx, len(words)))

        return sequences

    def _is_valid_callsign_format(self, callsign: str) -> bool:
        """
        Validate callsign format using amateur radio rules.

        Basic rules:
        - Minimum 3 characters
        - Maximum 8 characters (including portable indicators)
        - Contains at least one letter and one number
        - Number typically after prefix

        Args:
            callsign: Callsign to validate

        Returns:
            True if valid format
        """
        if not callsign or len(callsign) < 3 or len(callsign) > 8:
            return False

        # Must contain at least one letter and one digit
        has_letter = any(c.isalpha() for c in callsign)
        has_digit = any(c.isdigit() for c in callsign)

        if not (has_letter and has_digit):
            return False

        # Basic regex pattern for callsign
        # Prefix (1-2 letters), digit, suffix (1-4 letters/digits)
        pattern = r'^[A-Z]{1,2}\d[A-Z0-9]{1,4}$'

        return bool(re.match(pattern, callsign))

    def normalize_rst(self, text: str) -> Optional[str]:
        """
        Normalize RST report from text.

        Args:
            text: Text containing RST (e.g., "five nine", "59", "five niner")

        Returns:
            Normalized RST (e.g., "59") or None

        Example:
            >>> parser.normalize_rst("five nine")
            '59'
            >>> parser.normalize_rst("five niner niner")
            '599'
        """
        text = text.lower().strip()
        words = text.split()

        digits = []
        for word in words:
            if word in self.numbers:
                digits.append(self.numbers[word])
            elif word.isdigit() and len(word) == 1:
                digits.append(word)

        if not digits:
            return None

        rst = ''.join(digits)

        # SSB is typically 2 digits (RS), CW is 3 digits (RST)
        if len(rst) in [2, 3]:
            return rst

        return None


# Singleton instance for easy access
_default_parser = None


def get_parser() -> PhoneticParser:
    """Get default phonetic parser instance."""
    global _default_parser
    if _default_parser is None:
        _default_parser = PhoneticParser()
    return _default_parser


def parse_callsign(text: str, strict: bool = False) -> Optional[str]:
    """
    Convenience function to parse callsign from text.

    Args:
        text: Text containing phonetic callsign
        strict: If True, only accept valid callsign format

    Returns:
        Callsign or None
    """
    return get_parser().parse_callsign(text, strict=strict)


def parse_exchange(text: str) -> List[str]:
    """
    Convenience function to parse exchange from text.

    Args:
        text: Text containing phonetic exchange

    Returns:
        List of exchange elements
    """
    return get_parser().parse_exchange(text)
