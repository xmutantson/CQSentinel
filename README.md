# CQSentinel

CQSentinel is a Windows-focused ham radio application for scanning phone-band segments, transcribing received audio, and displaying candidate stations on a band map.

**Status: development preview.** The repository contains working components and offline regression tests, but a complete hardware and packaged-release acceptance run is still required. Callsigns and contest classifications are suggestions for an operator to verify.

Contest scores are heuristics, not calibrated probabilities. With voice identification disabled, scores are normalized over the available transcript evidence; missing speaker data does not count as evidence against contest activity. Adjust the threshold using representative recordings, and do not infer a running/searching operator role from an unavailable voice model.

## Current scope

- Radio CAT control through Hamlib/rigctld, with configurable band scans.
- Audio capture, noise reduction, speech detection, and speech transcription.
- Local Whisper, a self-hosted network Whisper endpoint, or an explicitly configured OpenAI transcription backend.
- Callsign extraction, contest classification, station transcripts, and per-band maps.
- Experimental SSB/FM auto-centering and contest profiles.

Voice fingerprinting is disabled: the previous Resemblyzer implementation was removed from the supported workflow. N3FJP integration modules exist, but automatic dupe/multiplier behavior requires separate end-to-end validation and is not a guaranteed feature of the scanning workflow. See [future voice work](docs/future/FUTURE_WORK_VOICE_ID.md).

## Installation

Start with [INSTALL.md](INSTALL.md). Use Python 3.10 in an isolated environment. From the repository root on Windows:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m cqsentinel.main
```

`setup.py` defines the pip dependencies, including **PyQt5**. `requirements.txt` installs that package with development and build tools. Optional CREPE/TensorFlow pitch detection is a separate extra.

For the optional OpenAI backend, also install `python -m pip install -e ".[cloud]"` in the active environment before configuring it.

There is no validated portable release bundled with this checkout. Do not assume that a ZIP or installer is available from GitHub Releases. Building one is a separate workflow described in [BUILD.md](BUILD.md); use `python scripts/build_windows.py` so the build includes Hamlib.

## First session

1. Configure the radio model, serial connection, and audio input in Settings.
2. Choose the transcription backend. A network server must already be available; cloud transcription requires an explicit API key.
3. Connect the radio and check that the frequency and incoming audio are correct.
4. Select bands and start scanning. Verify candidate callsigns against the transcript and received audio.
5. Stop scanning before changing the radio connection or audio devices. Apply any settings marked as requiring a restart by restarting the application.

A scan tunes the connected receiver. Use a separate receiver or stop the scan when you need manual control of that radio.

## Models, network use, and data

Local speech recognition can operate without a network after the required models are present. **Models are not included in the source checkout**; initial setup may download a large model. Network transcription sends audio to the configured server. OpenAI transcription sends audio to that service and can incur usage charges. These are distinct, explicitly selected backends, not an unconditional offline guarantee.

Settings are stored in `~/.cqsentinel/config.yaml`. Keep this file private: a configured OpenAI API key is currently stored with the settings. Do not attach it to bug reports. Report the backend type and a redacted error message instead.

## Development and validation

Run the offline regression suite from the repository root:

```powershell
python -B -m unittest discover -s tests -v
```

The suite uses synthetic audio and fake service/hardware boundaries. It does not establish radio compatibility, recognition accuracy, or packaged executable support. Scripts under `scripts/test/`, `scripts/test_hamlib.py`, and audio diagnostics may contact hardware; they are manual checks, not part of the offline suite.

Before distributing a build, validate it on a clean Windows machine, exercise Start/Stop/Skip and two-band scanning with the intended radio, and measure callsign precision and false detections on representative recordings. Model speed and auto-centering accuracy depend on the hardware and signal conditions; the repository does not establish universal performance guarantees.

## Documentation

- [Installation](INSTALL.md)
- [Quick start](docs/QUICKSTART.md)
- [Windows builds](BUILD.md)
- [Network transcription](docs/NETWORK_TRANSCRIPTION.md)
- [Documentation index](docs/README.md)
- [Original project plan](docs/PROJECT_PLAN.md) and [historical phase notes](docs/legacy/phases/)

Historical phase and research documents describe earlier designs; they are not release acceptance records. Contributions are welcome, especially reproducible offline tests, radio compatibility reports, and labeled contest recordings that you have permission to share.

## License

A license has not yet been selected. Choosing and adding one remains a maintainer decision.
