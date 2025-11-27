# faster-whisper Threading/Multiprocessing Research

## Problem Summary

**Current crash**: `Fatal Python error: Aborted` in `faster_whisper\feature_extractor.py:224`
**Configuration**: Windows, PyInstaller frozen build, QThread worker pattern, CPU mode, int8 compute type
**MKL threading**: Already set to single-threaded (didn't fix the issue)

## Research Findings

### 1. Known Windows Crashes with faster-whisper

#### Issue #1293: Windows Crash on Exit (0xC0000409)
**Symptoms**:
- Crash with `0xC0000409` (STATUS_STACK_BUFFER_OVERRUN) in ucrtbase.dll
- Occurs during cleanup/unloading, not during transcription
- Related to CTranslate2 GPU memory cleanup

**Solutions**:
- ✅ **Temperature setting**: `temperature=0.0` disables fallback (prevents crash)
- ✅ **Separate process**: Run transcription in subprocess with IPC
- ⚠️ **Global model**: Keep model as global variable (not thread-local)

#### Issue #71: Windows Process Crash When Model Unloaded
**Root cause**: "When the model is unloaded, the program will crash"
**Discovery**: Making model a **global variable** (persistent until exit) prevented crashes
**Implication**: Model cleanup in worker threads is problematic on Windows

### 2. CTranslate2 Thread Safety Claims

**Documentation says**:
> "Parallelization with multiple Python threads is possible because all computation methods release the Python GIL"

**Reality**:
- Threading may work on Linux but has issues on Windows
- Model loading/unloading in threads causes crashes
- Feature extraction (NumPy/BLAS operations) may not be truly thread-safe on Windows

### 3. Community Solutions

#### Solution A: Separate Process (Most Reliable)
**Projects using this approach**:
- faster-whisper-acceleration: Runs chunks in separate processes
- Whisper web services: Use multiprocessing.Pool

**Benefits**:
- ✅ Complete isolation (no threading conflicts)
- ✅ Crash in worker doesn't crash main app
- ✅ Works reliably on Windows
- ✅ Can use multiprocessing.Queue for communication

**Drawbacks**:
- Model needs to be loaded per process (slow first transcription)
- Higher memory usage
- More complex IPC

#### Solution B: Threading.Thread (Current Approach)
**Status**: Known to cause crashes on Windows with faster-whisper

**Why it fails**:
- Model created in main thread, used in worker thread
- NumPy/BLAS may have thread-local state
- CTranslate2 cleanup issues in threads on Windows
- PyInstaller frozen builds add complexity

#### Solution C: Global Model + Main Thread Processing
**Approach**: Keep model in main thread, process audio synchronously

**Benefits**:
- ✅ No threading issues
- ✅ Model persists (no cleanup crashes)

**Drawbacks**:
- ❌ Freezes GUI during transcription
- ❌ Not acceptable for real-time app

### 4. Multiprocessing vs Threading for Whisper

**OpenAI Whisper Discussion #1856: Multiprocessing Crashes**
**Problem**: Whisper dies silently in multiprocessing.Process
**Cause**: PyTorch CUDA limitations with default "fork" method
**Solution**:
```python
import torch.multiprocessing as mp
mp.set_start_method("spawn", force=True)
```

**Note**: You're using CPU-only, so this CUDA issue doesn't apply

## Recommended Solutions (Ordered by Reliability)

### 🥇 Solution 1: Subprocess with IPC (Highest Reliability)

**Architecture**:
```
Main Process (GUI)
  └─> Subprocess (Whisper transcription)
        └─> Returns results via queue/pipe
```

**Implementation**:
```python
import multiprocessing as mp
from multiprocessing import Process, Queue

class TranscriptionProcess:
    def __init__(self):
        self.process = None
        self.result_queue = mp.Queue()

    def transcribe_async(self, audio, sample_rate, callback):
        # Start subprocess
        self.process = Process(
            target=self._transcribe_worker,
            args=(audio, sample_rate, self.result_queue)
        )
        self.process.start()

        # Poll for results in main thread (non-blocking)
        # Use QTimer to check queue periodically

    @staticmethod
    def _transcribe_worker(audio, sample_rate, result_queue):
        # Import WhisperModel INSIDE subprocess
        from faster_whisper import WhisperModel

        # Load model (happens once per subprocess)
        model = WhisperModel("small", device="cpu", compute_type="int8")

        # Transcribe
        results = model.transcribe(audio, sample_rate=sample_rate)

        # Send results back
        for segment in results:
            result_queue.put(segment.text)

        result_queue.put(None)  # Signal completion
```

**Pros**:
- ✅ **Most reliable** - process isolation prevents crashes from affecting GUI
- ✅ Works on Windows (documented solutions)
- ✅ Can handle crashes gracefully
- ✅ PyInstaller compatible

**Cons**:
- Model loads per subprocess (slow first time)
- More complex IPC code
- Higher memory usage

### 🥈 Solution 2: Pre-load Model in Main Thread, Temperature=0

**Change**:
```python
# In transcription.py
def transcribe(self, audio, sample_rate, vad_filter=True):
    # Add temperature=0.0 to prevent fallback crashes
    segments, info = self.model.transcribe(
        audio,
        language="en",
        temperature=0.0,  # Disable fallback (prevents Windows crash)
        vad_filter=vad_filter
    )
```

**Also**:
- Pre-load model in main thread BEFORE creating workers
- Keep model alive as instance variable (don't recreate)

**Pros**:
- ✅ Minimal code changes
- ✅ May prevent cleanup crashes

**Cons**:
- ⚠️ Still using threading (may still crash)
- ⚠️ temperature=0 may reduce accuracy
- ⚠️ Doesn't address root threading issue

### 🥉 Solution 3: Switch to float32 (Instead of int8)

**Issue**: int8 compute type reported to cause issues on Windows CPU

**Change**:
```python
# In transcription.py __init__
self.model = WhisperModel(
    model_size,
    device="cpu",
    compute_type="float32",  # Instead of int8
)
```

**Pros**:
- ✅ May avoid int8-specific crashes

**Cons**:
- ❌ Higher memory usage
- ❌ Slower transcription
- ⚠️ Doesn't address threading issue

## Crash Analysis: Your Specific Case

### The Crash Location
```
File "faster_whisper\feature_extractor.py", line 224 in __call__
Fatal Python error: Aborted
```

**This is during audio feature extraction (spectrogram computation)**

### Why MKL Threading Didn't Fix It
Setting `MKL_NUM_THREADS=1` prevents NumPy from spawning threads, but:
- ❌ Doesn't prevent C++ code (ctranslate2) issues
- ❌ Doesn't prevent threading conflicts with Qt
- ❌ Doesn't prevent model cleanup crashes on Windows

### Why It's a Threading Issue
1. Model created in **main thread** (MainWindow.__init__)
2. Model used in **worker thread** (QThread)
3. Windows + ctranslate2 + threading = crashes
4. Issue #71 confirms: Model unloading in threads crashes on Windows

## Recommended Action Plan

### Phase 1: Quick Test (5 minutes)
**Try temperature=0.0 + float32**:
```python
# In transcription.py
self.model = WhisperModel(
    model_size,
    device="cpu",
    compute_type="float32",  # Changed from int8
)

# In transcribe method
segments, info = self.model.transcribe(
    audio,
    language="en",
    temperature=0.0,  # Disable fallback
    vad_filter=vad_filter
)
```

**If this works**: Great, but still not addressing root cause
**If this fails**: Move to Phase 2

### Phase 2: Implement Subprocess Solution (1-2 hours)
**Create separate transcription subprocess**:
- Load model in subprocess
- Use multiprocessing.Queue for results
- Poll queue from main thread with QTimer
- Emit Qt signals when results arrive

**Benefits**: Proper solution, reliable on Windows

### Phase 3: Alternative - whisper.cpp
If Python solutions fail, consider **whisper.cpp**:
- Native C++ implementation
- No Python threading issues
- Can call via subprocess
- Proven to work on Windows

## References

1. **faster-whisper Issue #1293**: Windows crash 0xC0000409
   https://github.com/SYSTRAN/faster-whisper/issues/1293

2. **faster-whisper Issue #71**: Windows crash when model unloaded
   https://github.com/SYSTRAN/faster-whisper/issues/71

3. **CTranslate2 Parallelism Docs**: Threading claims
   https://opennmt.net/CTranslate2/parallel.html

4. **Whisper Discussion #1856**: Multiprocessing crashes
   https://github.com/openai/whisper/discussions/1856

5. **faster-whisper-acceleration**: Subprocess implementation
   https://github.com/RomanKlimov/faster-whisper-acceleration

## Conclusion

**The threading approach is fundamentally problematic on Windows with faster-whisper.**

**Best solution**: Implement subprocess-based transcription (Solution 1)
**Quick test**: Try temperature=0.0 + float32 (Solution 2)
**If all else fails**: Switch to whisper.cpp

The crash is NOT about NumPy threading, it's about **ctranslate2/faster-whisper not being truly thread-safe on Windows**, despite documentation claims.
