# CQSentinel Crash Risk Analysis

## Current Diagnostic Added
Added `os.pipe()` test at line 247-262 in `main_window.py` to verify if pipe creation works in PyInstaller frozen builds on Windows.

## Next Most Likely Crash Points (Ordered by Risk)

### 1. **WhisperModel Loading in Worker Thread** (HIGH RISK)
**Location**: `cqsentinel/speech/transcription.py:61-86` (`_load_model()`)
**Called from**: First call to `self._transcriber.transcribe()` at `main_window.py:403`

**Why it could crash:**
- **C++ library initialization**: `faster-whisper` imports `ctranslate2`, a C++ library
- **Model file loading**: Downloads/loads model files (~244 MB for "small")
- **Memory allocation**: Large model allocation in worker thread
- **CUDA detection**: Even CPU-only builds check for CUDA availability
- **File I/O in redirected environment**: Model loading happens AFTER we redirect stderr

**Risk Indicators:**
```python
from faster_whisper import WhisperModel  # C++ import
self.model = WhisperModel(
    self.model_size,
    device=self.device,
    compute_type=self.compute_type,
    download_root=None  # Uses default cache
)
```

**Diagnostic to add:**
```python
logger.info("[WORKER] About to load WhisperModel...")
logger.info(f"[WORKER] Model: {self.model_size}, device: {self.device}, compute: {self.compute_type}")
self._transcriber._load_model()  # Explicit load before transcription
logger.info("[WORKER] WhisperModel loaded successfully")
```

---

### 2. **Resemblyzer VoiceEncoder Loading** (HIGH RISK)
**Location**: `cqsentinel/voice/embeddings.py:60-75` (`_ensure_model_loaded()`)
**Called from**: `main_window.py:363` (`detect_speaker_changes`)

**Why it could crash:**
- **PyTorch model loading**: Resemblyzer uses PyTorch underneath
- **Downloads model from hub**: ~60 MB download on first use
- **torch.jit operations**: May try to use JIT compilation
- **GPU detection**: PyTorch checks for CUDA even in CPU mode

**Risk Indicators:**
```python
from resemblyzer import VoiceEncoder  # Imports PyTorch
self.encoder = VoiceEncoder()  # Downloads and loads model
```

**Order of execution:**
1. Speaker detection runs BEFORE transcription (line 363)
2. This means Resemblyzer loads BEFORE faster-whisper
3. **This is the FIRST PyTorch model to load in the worker thread**

**Diagnostic to add:**
```python
logger.info("[WORKER] About to load Resemblyzer VoiceEncoder...")
self._ensure_model_loaded()
logger.info("[WORKER] Resemblyzer VoiceEncoder loaded successfully")
```

---

### 3. **PyTorch Import Issues** (MEDIUM-HIGH RISK)
**Location**: Multiple files import `torch`
**Primary risk**: `resemblyzer` imports `torch` internally

**Why it could crash:**
- **Module not found**: If PyInstaller didn't package torch correctly
- **DLL loading**: PyTorch C++ extensions (libtorch, mkl, etc.)
- **CUDA stub errors**: Even CPU builds import cuda stubs
- **Version mismatches**: Between torch and its dependencies

**Known from previous work:**
- Spec file excludes were causing "No module named 'torch.cuda'" errors
- Fixed by removing torch.cuda from excludes
- Changed module_collection_mode to 'pyz+py' for JIT support

**What to watch for:**
```
ModuleNotFoundError: No module named 'torch'
ImportError: DLL load failed while importing _C
OSError: [WinError 126] The specified module could not be found
```

---

### 4. **ctranslate2 C++ Initialization** (MEDIUM-HIGH RISK)
**Location**: During `WhisperModel()` instantiation
**Called from**: `transcription.py:71`

**Why it could crash:**
- **Native C++ library**: ctranslate2 is pure C++, not Python
- **CPU instruction sets**: May check for AVX, AVX2, AVX512
- **Thread affinity**: C++ code may not expect Qt thread environment
- **Memory alignment**: C++ code has strict alignment requirements
- **Exception handling**: C++ exceptions may not propagate correctly

**Potential crash scenarios:**
1. **Segfault in C++ code** - Would show in faulthandler output
2. **C++ assertion failure** - May write to stderr before aborting
3. **Illegal instruction** - If CPU doesn't support required instructions
4. **Access violation** - Memory access errors in C++ code

---

### 5. **NumPy Operations with Redirected FDs** (MEDIUM RISK)
**Location**: Throughout voice embedding and transcription
**Examples**:
- `main_window.py:363` - `detect_speaker_changes()` processes audio arrays
- `embeddings.py:137` - `self.encoder.embed_utterance(processed)`
- `transcription.py:117` - `self.model.transcribe(audio, ...)`

**Why it could crash:**
- **BLAS/LAPACK libraries**: NumPy uses C/Fortran libraries underneath
- **OpenMP threading**: NumPy may spawn additional threads
- **Memory-mapped files**: Some NumPy operations use mmap
- **Signal handling**: BLAS libraries may install signal handlers

**Risk is MEDIUM because:**
- NumPy operations happen AFTER fd redirection
- C libraries write to stderr for warnings/errors
- Our fd redirection should catch these

---

### 6. **Qt Signal Emissions from Worker Thread** (LOW-MEDIUM RISK)
**Location**: `main_window.py:427` - `self.transcription_ready.emit()`
**Location**: `main_window.py:430` - `self.transcription_complete.emit()`

**Why it could crash:**
- **Iterator exhaustion**: `transcripts` is a generator from faster-whisper
- **Signal during shutdown**: Window might close while emitting
- **Large text strings**: Very long transcriptions might cause issues

**Risk is LOW-MEDIUM because:**
- We're using proper Qt signals (thread-safe)
- Worker is on QThread with moveToThread()
- Signals are the CORRECT way to communicate with main thread

**What to watch for:**
- Silent failure (no signal received)
- Window closes during transcription
- Partial results lost

---

### 7. **File Descriptor Cleanup on Windows** (LOW RISK)
**Location**: `main_window.py:456-467` (finally block)
**Operations**: `os.dup2()`, `os.close()`, `os.unlink()`

**Why it could crash:**
- **Double close**: Closing already-closed fd
- **Invalid fd**: Restoring to invalid fd number
- **File locked**: Temp file still open by tail thread
- **Permission error**: Can't delete temp file

**Risk is LOW because:**
- We have try/except around each operation
- Errors are logged but not raised
- finally block always runs

---

## Crash Prediction Order

Based on code execution flow:

1. **Logger setup** (lines 200-245) - ✅ Has extensive diagnostics
2. **os.pipe() test** (lines 247-262) - ✅ NEW DIAGNOSTIC ADDED
3. **Stdout/stderr redirection** (lines 264-353) - ✅ Has extensive logging
4. **🔴 Resemblyzer loading** (line 363 → embeddings.py:60) - **NO DIAGNOSTICS**
5. **🔴 WhisperModel loading** (line 403 → transcription.py:61) - **NO DIAGNOSTICS**
6. **Speaker detection** (lines 363-397) - Has try/except, logs errors
7. **Transcription** (lines 403-414) - Has lock, no other protection
8. **Result emission** (lines 417-429) - Should be safe
9. **Cleanup** (lines 432-467) - Has try/except

## Recommended Next Diagnostics

### Priority 1: Add diagnostics BEFORE model loading

In `main_window.py` around line 355:

```python
try:
    logger.info(f"Transcribing {len(self._audio)/self._sample_rate:.1f}s of speech...")

    # DIAGNOSTIC: Test if voice embedder and transcriber are already loaded
    logger.info("[WORKER] Checking model states...")
    if self._voice_embedder:
        logger.info(f"[WORKER] VoiceEmbedder present, encoder loaded: {self._voice_embedder.encoder is not None}")
    if self._transcriber:
        logger.info(f"[WORKER] Transcriber present, model loaded: {self._transcriber.model is not None}")

    # Identify speaker(s) using sliding window voice embeddings
    speaker_labels = []
    if self._voice_embedder and self._voice_db:
        try:
            logger.info("[WORKER] About to call detect_speaker_changes (may load Resemblyzer)...")
            # Detect speaker changes
            speaker_segments = self._voice_embedder.detect_speaker_changes(
```

### Priority 2: Add diagnostics IN model loading

In `cqsentinel/speech/transcription.py` at line 61:

```python
def _load_model(self):
    """Lazy-load faster-whisper model"""
    if self.model is not None:
        return

    try:
        logger.info(f"[TRANSCRIBER] Loading Whisper {self.model_size} model...")
        logger.info(f"[TRANSCRIBER] Device: {self.device}, Compute type: {self.compute_type}")

        logger.info("[TRANSCRIBER] Importing faster_whisper.WhisperModel...")
        from faster_whisper import WhisperModel
        logger.info("[TRANSCRIBER] Import successful")

        logger.info("[TRANSCRIBER] Instantiating WhisperModel...")
        self.model = WhisperModel(
            self.model_size,
            device=self.device,
            compute_type=self.compute_type,
            download_root=None  # Use default cache
        )
        logger.info(f"[TRANSCRIBER] WhisperModel instantiated successfully")
```

In `cqsentinel/voice/embeddings.py` at line 60:

```python
def _ensure_model_loaded(self):
    """Lazy-load the Resemblyzer model."""
    if self.encoder is None:
        try:
            logger.info("[EMBEDDER] About to import resemblyzer.VoiceEncoder...")
            from resemblyzer import VoiceEncoder
            logger.info("[EMBEDDER] Import successful")

            logger.info("[EMBEDDER] Loading Resemblyzer model (may download ~60MB)...")
            self.encoder = VoiceEncoder()
            logger.info("[EMBEDDER] Resemblyzer model loaded successfully")
```

## Expected Crash Signatures

### If Resemblyzer crashes:
```
[WORKER] About to call detect_speaker_changes (may load Resemblyzer)...
[EMBEDDER] About to import resemblyzer.VoiceEncoder...
(crash or silence)
```

### If WhisperModel crashes:
```
[WORKER] About to transcribe with WhisperModel...
[TRANSCRIBER] Importing faster_whisper.WhisperModel...
(crash or silence)
```

### If it's actually os.pipe():
```
[WORKER] DIAGNOSTIC: Testing os.pipe() functionality...
(crash or silence)
```

## Windows Event Viewer Clues

If the application crashes, check Event Viewer for:
- **Application Error (1000)**: Module name that crashed (e.g., ctranslate2.dll, torch_cpu.dll)
- **Exception code**:
  - `0xc0000005` = Access violation (memory error)
  - `0xc000001d` = Illegal instruction (CPU feature not supported)
  - `0xc0000409` = Stack buffer overrun
- **Faulting module**: Which DLL crashed (Python.exe, Qt5Core.dll, torch_cpu.dll, etc.)
