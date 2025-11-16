"""
Voice database for operator tracking and identification.

Maintains a persistent database of operator voice fingerprints, allowing
recognition across frequencies and sessions.
"""

import logging
import pickle
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class OperatorVoice:
    """
    Represents a tracked operator with voice fingerprint and metadata.
    """
    # Identification
    voice_id: str  # UUID
    callsign: Optional[str] = None  # May be None until confirmed

    # Voice fingerprint
    embedding: np.ndarray = field(default_factory=lambda: np.zeros(256))  # 256-dim
    embedding_samples: List[np.ndarray] = field(default_factory=list)  # All samples

    # Metadata
    first_heard: datetime = field(default_factory=datetime.now)
    last_heard: datetime = field(default_factory=datetime.now)
    total_airtime_seconds: float = 0.0

    # Activity
    frequencies_heard: List[float] = field(default_factory=list)  # Hz
    estimated_qso_count: int = 0
    is_run_station: bool = False

    # Contest data
    exchange: Optional[str] = None  # e.g., "2A WWA"
    contestness_score: float = 0.0  # 0-100

    # Status
    worked: bool = False
    worked_timestamp: Optional[datetime] = None

    def __post_init__(self):
        """Ensure embedding is numpy array."""
        if isinstance(self.embedding, list):
            self.embedding = np.array(self.embedding)

    @property
    def duration_heard(self) -> float:
        """Total time between first and last heard (seconds)."""
        if self.first_heard and self.last_heard:
            return (self.last_heard - self.first_heard).total_seconds()
        return 0.0

    @property
    def frequency_count(self) -> int:
        """Number of unique frequencies heard on."""
        return len(set(self.frequencies_heard))

    def update_embedding(self, new_embedding: np.ndarray, max_samples: int = 10):
        """
        Update the operator's embedding with a new sample.

        Uses a running average of recent samples for improved accuracy.

        Args:
            new_embedding: New 256-dim embedding
            max_samples: Maximum samples to keep (default: 10)
        """
        self.embedding_samples.append(new_embedding)

        # Keep only recent samples
        if len(self.embedding_samples) > max_samples:
            self.embedding_samples = self.embedding_samples[-max_samples:]

        # Update embedding as mean of all samples
        self.embedding = np.mean(self.embedding_samples, axis=0)


class VoiceDatabase:
    """
    Database for tracking operator voice fingerprints.

    Maintains persistent storage of operator voices with:
    - Voice fingerprint matching
    - Activity tracking
    - Worked status
    - Contest metadata

    Usage:
        db = VoiceDatabase()
        db.load('voice_db.pkl')

        # Match a new voice
        match = db.find_matching_voice(embedding, threshold=0.75)
        if match:
            print(f"Matched operator: {match.callsign}")
        else:
            db.add_operator(embedding, metadata={'frequency': 14250000})

        db.save('voice_db.pkl')
    """

    def __init__(self):
        """Initialize an empty voice database."""
        self.operators: Dict[str, OperatorVoice] = {}
        self.created_at: datetime = datetime.now()
        self.last_modified: datetime = datetime.now()

        logger.info("VoiceDatabase initialized")

    def get_age_days(self) -> float:
        """
        Get the age of the database in days.

        Returns:
            Age in days since creation
        """
        return (datetime.now() - self.created_at).total_seconds() / 86400

    def find_matching_voice(
        self,
        embedding: np.ndarray,
        threshold: float = 0.75
    ) -> Optional[Tuple[str, float]]:
        """
        Find operator with matching voice embedding.

        Args:
            embedding: Voice embedding to match (256-dim)
            threshold: Similarity threshold (0-1, default: 0.75)

        Returns:
            Tuple of (voice_id, similarity) if match found, else None

        Similarity thresholds:
            - 0.85+: Very confident match
            - 0.75-0.85: Confident match
            - 0.65-0.75: Possible match
            - < 0.65: Different speaker

        Example:
            >>> db = VoiceDatabase()
            >>> match = db.find_matching_voice(embedding, threshold=0.75)
            >>> if match:
            ...     voice_id, similarity = match
            ...     print(f"Matched {voice_id} with {similarity:.2f} similarity")
        """
        best_match_id = None
        best_similarity = 0.0

        for voice_id, operator in self.operators.items():
            similarity = self._cosine_similarity(embedding, operator.embedding)

            if similarity > best_similarity:
                best_similarity = similarity
                best_match_id = voice_id

        if best_similarity >= threshold:
            logger.debug(
                f"Found match: {best_match_id} (similarity: {best_similarity:.3f})"
            )
            return (best_match_id, best_similarity)

        logger.debug(
            f"No match found (best similarity: {best_similarity:.3f} < {threshold:.3f})"
        )
        return None

    def add_operator(
        self,
        embedding: np.ndarray,
        metadata: Optional[Dict] = None,
        voice_id: Optional[str] = None
    ) -> str:
        """
        Add a new operator to the database.

        Args:
            embedding: Voice embedding (256-dim)
            metadata: Optional metadata dict with keys:
                - callsign: str
                - frequency: float (Hz)
                - exchange: str
                - airtime: float (seconds)
                - contestness_score: float
                - is_run_station: bool
            voice_id: Optional voice ID (if not provided, generates new UUID)

        Returns:
            voice_id: UUID for the new operator

        Example:
            >>> db = VoiceDatabase()
            >>> voice_id = db.add_operator(
            ...     embedding,
            ...     metadata={'callsign': 'W1AW', 'frequency': 14250000}
            ... )
        """
        metadata = metadata or {}

        if voice_id is None:
            voice_id = str(uuid.uuid4())
        now = datetime.now()

        operator = OperatorVoice(
            voice_id=voice_id,
            callsign=metadata.get('callsign'),
            embedding=embedding,
            embedding_samples=[embedding],
            first_heard=now,
            last_heard=now,
            total_airtime_seconds=metadata.get('airtime', 0.0),
            frequencies_heard=[metadata.get('frequency', 0.0)],
            estimated_qso_count=0,
            is_run_station=metadata.get('is_run_station', False),
            exchange=metadata.get('exchange'),
            contestness_score=metadata.get('contestness_score', 0.0),
            worked=False,
            worked_timestamp=None
        )

        self.operators[voice_id] = operator
        self.last_modified = now

        logger.info(
            f"Added new operator {voice_id} "
            f"(callsign: {operator.callsign or 'Unknown'})"
        )

        return voice_id

    def update_operator(
        self,
        voice_id: str,
        embedding: Optional[np.ndarray] = None,
        metadata: Optional[Dict] = None
    ) -> bool:
        """
        Update an existing operator's information.

        Args:
            voice_id: Operator's voice ID
            embedding: New voice embedding (optional)
            metadata: Metadata to update (same keys as add_operator)

        Returns:
            True if updated, False if operator not found

        Example:
            >>> db.update_operator(
            ...     voice_id,
            ...     embedding=new_embedding,
            ...     metadata={'callsign': 'W1AW', 'frequency': 14287500}
            ... )
        """
        if voice_id not in self.operators:
            logger.warning(f"Operator {voice_id} not found")
            return False

        operator = self.operators[voice_id]
        metadata = metadata or {}

        # Update timestamp
        operator.last_heard = datetime.now()
        self.last_modified = datetime.now()

        # Update embedding
        if embedding is not None:
            operator.update_embedding(embedding)

        # Update metadata
        if 'callsign' in metadata and metadata['callsign']:
            operator.callsign = metadata['callsign']

        if 'frequency' in metadata:
            operator.frequencies_heard.append(metadata['frequency'])

        if 'airtime' in metadata:
            operator.total_airtime_seconds += metadata['airtime']

        if 'exchange' in metadata and metadata['exchange']:
            operator.exchange = metadata['exchange']

        if 'contestness_score' in metadata:
            # Update as running average
            old_score = operator.contestness_score
            new_score = metadata['contestness_score']
            operator.contestness_score = (old_score + new_score) / 2

        if 'is_run_station' in metadata:
            operator.is_run_station = metadata['is_run_station']

        logger.debug(f"Updated operator {voice_id}")
        return True

    def add_or_update(
        self,
        embedding: np.ndarray,
        metadata: Optional[Dict] = None,
        threshold: float = 0.75
    ) -> Tuple[str, bool]:
        """
        Add a new operator or update existing if match found.

        Args:
            embedding: Voice embedding
            metadata: Operator metadata
            threshold: Similarity threshold for matching

        Returns:
            Tuple of (voice_id, is_new)
                voice_id: Operator's voice ID
                is_new: True if new operator, False if updated existing

        Example:
            >>> voice_id, is_new = db.add_or_update(embedding, metadata)
            >>> if is_new:
            ...     print("New operator detected")
            ... else:
            ...     print(f"Updated operator {voice_id}")
        """
        match = self.find_matching_voice(embedding, threshold)

        if match:
            voice_id, similarity = match
            self.update_operator(voice_id, embedding, metadata)
            return (voice_id, False)
        else:
            voice_id = self.add_operator(embedding, metadata)
            return (voice_id, True)

    def mark_worked(self, voice_id: str) -> bool:
        """
        Mark an operator as worked.

        Args:
            voice_id: Operator's voice ID

        Returns:
            True if marked, False if operator not found
        """
        if voice_id not in self.operators:
            logger.warning(f"Operator {voice_id} not found")
            return False

        operator = self.operators[voice_id]
        operator.worked = True
        operator.worked_timestamp = datetime.now()
        self.last_modified = datetime.now()

        logger.info(
            f"Marked operator {voice_id} as worked "
            f"(callsign: {operator.callsign or 'Unknown'})"
        )

        return True

    def get_operator(self, voice_id: str) -> Optional[OperatorVoice]:
        """Get operator by voice ID."""
        return self.operators.get(voice_id)

    def get_all_operators(self) -> List[OperatorVoice]:
        """Get list of all operators."""
        return list(self.operators.values())

    def get_worked_operators(self) -> List[OperatorVoice]:
        """Get list of worked operators."""
        return [op for op in self.operators.values() if op.worked]

    def get_unworked_operators(self) -> List[OperatorVoice]:
        """Get list of unworked operators."""
        return [op for op in self.operators.values() if not op.worked]

    def reset_worked_status(self):
        """Reset worked status for all operators (e.g., new contest)."""
        for operator in self.operators.values():
            operator.worked = False
            operator.worked_timestamp = None

        self.last_modified = datetime.now()
        logger.info("Reset worked status for all operators")

    def clear(self):
        """Clear all operators from the database."""
        count = len(self.operators)
        self.operators.clear()
        self.created_at = datetime.now()
        self.last_modified = datetime.now()

        logger.info(f"Cleared database ({count} operators removed)")

    def save(self, filepath: str):
        """
        Save database to file using pickle.

        Args:
            filepath: Path to save file

        Example:
            >>> db.save('voice_database.pkl')
        """
        try:
            filepath = Path(filepath)
            filepath.parent.mkdir(parents=True, exist_ok=True)

            with open(filepath, 'wb') as f:
                pickle.dump(self, f, protocol=pickle.HIGHEST_PROTOCOL)

            logger.info(
                f"Saved voice database to {filepath} "
                f"({len(self.operators)} operators)"
            )

        except Exception as e:
            logger.error(f"Failed to save database to {filepath}: {e}")
            raise

    @staticmethod
    def load(filepath: str) -> 'VoiceDatabase':
        """
        Load database from file.

        Args:
            filepath: Path to database file

        Returns:
            VoiceDatabase instance

        Example:
            >>> db = VoiceDatabase.load('voice_database.pkl')
            >>> print(f"Loaded {len(db.operators)} operators")
        """
        try:
            filepath = Path(filepath)

            if not filepath.exists():
                logger.warning(f"Database file {filepath} not found, creating new")
                return VoiceDatabase()

            with open(filepath, 'rb') as f:
                db = pickle.load(f)

            logger.info(
                f"Loaded voice database from {filepath} "
                f"({len(db.operators)} operators, "
                f"age: {db.get_age_days():.1f} days)"
            )

            # Warn if database is old
            if db.get_age_days() > 5:
                logger.warning(
                    f"Voice database is {db.get_age_days():.1f} days old. "
                    "Consider resetting for current contest."
                )

            return db

        except Exception as e:
            logger.error(f"Failed to load database from {filepath}: {e}")
            logger.info("Creating new database")
            return VoiceDatabase()

    def _cosine_similarity(
        self,
        embedding1: np.ndarray,
        embedding2: np.ndarray
    ) -> float:
        """
        Compute cosine similarity between two embeddings.

        Args:
            embedding1: First embedding
            embedding2: Second embedding

        Returns:
            Similarity score (0-1)
        """
        norm1 = np.linalg.norm(embedding1)
        norm2 = np.linalg.norm(embedding2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        similarity = np.dot(embedding1, embedding2) / (norm1 * norm2)
        return float(np.clip(similarity, 0.0, 1.0))

    def get_statistics(self) -> Dict:
        """
        Get database statistics.

        Returns:
            Dictionary with statistics
        """
        ops = self.operators.values()
        worked = self.get_worked_operators()

        return {
            'total_operators': len(self.operators),
            'worked_operators': len(worked),
            'unworked_operators': len(ops) - len(worked),
            'operators_with_callsigns': sum(1 for op in ops if op.callsign),
            'operators_without_callsigns': sum(1 for op in ops if not op.callsign),
            'age_days': self.get_age_days(),
            'created_at': self.created_at,
            'last_modified': self.last_modified,
        }

    def __len__(self) -> int:
        """Return number of operators in database."""
        return len(self.operators)

    def __repr__(self) -> str:
        """String representation of database."""
        stats = self.get_statistics()
        return (
            f"VoiceDatabase("
            f"operators={stats['total_operators']}, "
            f"worked={stats['worked_operators']}, "
            f"age={stats['age_days']:.1f}d)"
        )
