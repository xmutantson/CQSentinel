# Future Work: Custom SSB Voice Identification Model

## Background

Amateur radio SSB (Single Sideband) transmissions use a narrow bandwidth of 300-3000 Hz, which strips away many distinguishing voice features present in full-bandwidth speech. Generic speaker embedding models like Resemblyzer, trained on wideband audio (50-8000+ Hz), cannot reliably distinguish between SSB voices - often scoring 0.90+ similarity between completely different speakers.

This document outlines the project scope for developing a custom voice embedding model specifically trained on SSB audio.

## Current Approach

CQSentinel currently relies on **callsign extraction** as the primary method for station identification:
- Phonetic parsing (NATO alphabet recognition)
- Pattern matching for callsign formats
- Frequency + callsign correlation
- Behavioral analysis (CQ patterns, QSO detection)

## Future: Custom SSB Voice Model

### Data Requirements

**Minimum Viable Dataset:**
- 50-100 unique speakers (amateur radio operators)
- 5-10 minutes of audio per speaker
- Multiple sessions per speaker (different days/conditions)
- **Total: ~10-15 hours of labeled SSB audio**

**Good Performance:**
- 200-500 speakers
- 10-20 minutes per speaker across multiple sessions
- Varied conditions (different bands, propagation, equipment)
- **Total: ~50-100 hours of labeled SSB audio**

**Excellent Performance:**
- 1000+ speakers
- 20+ minutes per speaker
- Cross-band recordings (same person on 20m, 40m, etc.)
- **Total: 300+ hours of labeled SSB audio**

### Data Collection Strategy

**Challenge:** The hard part isn't recording hours - it's **confirmed labeling** (callsign-to-voice mapping).

**Potential Sources:**
1. **Contest recordings** - ARRL SS, CQ WW, CQWPX with known run stations
2. **QSO parties** - Recognizable big gun stations
3. **Club member contributions** - Volunteer recordings with verified callsigns
4. **Your own logged QSOs** - With audio recording enabled
5. **WebSDR archives** - Public recordings with known station activity

**Labeling Requirements:**
- Confirmed callsign for each audio segment
- Same operator recorded multiple times (different sessions)
- Different equipment/bands when possible
- Various QRM/QRN conditions

### Technical Implementation

#### Phase 1: Data Collection (2-4 weeks)
```
Tasks:
- Set up contest recording infrastructure
- Extract segments by callsign (manual or semi-automated)
- Clean and label dataset (remove noise-only segments)
- Organize into training/validation/test splits
- ~20 hours of human work + wait time for contests
```

#### Phase 2: Model Training (1-2 weeks)
```
Tasks:
- Fine-tune ECAPA-TDNN backbone (better than Resemblyzer)
- SSB-specific preprocessing pipeline
- Cross-validation on held-out speakers
- Hyperparameter tuning (embedding size, loss function)
- ~40 hours GPU compute, ~10 hours human oversight
```

#### Phase 3: Integration (1 week)
```
Tasks:
- Replace Resemblyzer with custom model in workers
- Adjust embedding dimensions if different
- Test in production with real contest conditions
- Tune similarity thresholds for SSB
- ~20 hours development/testing
```

**Total Project Timeline: 1-2 months, 50-100 hours work**

### Infrastructure Requirements

**Training Environment:**
- GPU with 8+ GB VRAM (RTX 3070 or better, RTX 4080 ideal)
- Or cloud GPU: Google Colab Pro (~$10/month), AWS/GCP (~$50-100 total)
- PyTorch 2.0+ and SpeechBrain framework
- ~100 GB storage for audio dataset
- Python environment with librosa, torchaudio

**Inference (Production):**
- ECAPA-TDNN: ~100-150 MB RAM per worker
- Similar footprint to current Resemblyzer (~17 MB model)
- No GPU required for inference (CPU only)
- Embedding computation: ~50-100ms per segment

### Model Architecture Options

**1. ECAPA-TDNN (Recommended)**
- State-of-the-art speaker embedding
- Better handles degraded audio than x-vectors
- SpeechBrain provides pre-trained weights
- Can fine-tune on SSB data

**2. ResNet-based Speaker Encoder**
- Simpler architecture
- Faster inference
- May need more data to train well

**3. Conformer-based**
- Latest architecture
- Best performance but higher resource usage
- Overkill for this application

### Expected Performance

**With 50-100 hours of SSB audio:**
- 70-80% accuracy on known speakers
- Still struggles with very similar-sounding operators
- Significantly better than generic Resemblyzer (~50-60%)

**With 300+ hours:**
- 85-90% accuracy achievable
- Handles band/propagation variations well
- Cross-session recognition reliable
- Worth the investment for serious contest use

### Alternative Approach: Semi-Supervised Learning

Lower effort, builds dataset organically:

1. **Run current callsign-based system**
2. **Log all transcriptions with audio segments**
3. **Operator manually confirms/corrects** callsign assignments in GUI
4. **Export corrected dataset** periodically
5. **Retrain model** on accumulated confirmed data
6. **Deploy updated model** back to production

This creates a feedback loop where the system improves over time with minimal upfront data collection effort.

### Integration with CQSentinel

**Current (Callsign-Based):**
```
Audio → Whisper → Text → Callsign Extraction → Station ID
```

**Future (Voice + Callsign):**
```
Audio → Whisper → Text → Callsign Extraction ─┐
  └──→ Voice Encoder → Embedding ───────────────┼──→ Station ID
                                                │
                                        (Ensemble voting)
```

Benefits of combined approach:
- Voice confirms callsign when heard
- Voice identifies when callsign not spoken
- Callsign provides ground truth for voice learning
- More robust than either method alone

### Community Contribution Opportunity

A well-trained SSB voice model would be valuable to the entire amateur radio community:

- **Open-source release** of trained model weights
- **Dataset sharing** (with consent) for community training
- **Paper publication** documenting approach and results
- **Integration with other logging software** (N1MM, DXLog, etc.)

This could become the definitive solution for SSB speaker identification in contesting.

### Recommended Path Forward

**Short Term (Current):**
- Focus on callsign extraction accuracy
- Use phonetic parsing improvements
- Track stations by frequency + callsign
- No voice fingerprinting

**Medium Term (1-2 months):**
- Collect labeled SSB data during major contests
- Try ECAPA-TDNN pre-trained (see if any improvement)
- Evaluate if custom training is justified

**Long Term (3-6 months):**
- If ECAPA-TDNN helps but not enough, proceed with custom training
- Build semi-supervised feedback loop
- Share model with community

### Resources

**SpeechBrain Framework:**
- https://speechbrain.github.io/
- Pre-trained ECAPA-TDNN models
- Easy fine-tuning pipeline

**Datasets (for pre-training knowledge):**
- VoxCeleb (general speaker recognition)
- NIST SRE (telephone speech - closer to SSB)
- LibriSpeech (clean speech baseline)

**SSB-Specific Considerations:**
- Apply SSB bandpass filter (300-3000 Hz) to training data
- Add simulated QRM/QRN for robustness
- Include various AGC and compression artifacts

---

*This document will be updated as the project progresses and more information becomes available.*
