# CQSentinel installation

CQSentinel is a development preview, primarily targeting Windows. This guide installs from source; a validated portable ZIP/installer is not currently supplied by the repository. Use [BUILD.md](BUILD.md) only if you intend to create and validate a distribution.

## Windows: isolated Python environment

Use Python 3.10 for the current dependency compatibility bounds. Clone the repository, change to its root, and keep all installs inside the new environment:

```powershell
git clone https://github.com/xmutantson/CQSentinel.git
cd CQSentinel
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m cqsentinel.main
```

The requirements file delegates to `setup.py`, the authoritative pip dependency definition. It installs PyQt5, both existing Whisper implementations, audio dependencies, and development/build extras. It does not install optional CREPE/TensorFlow pitch detection. Installation may download large packages; a network backend currently does not remove the application's local audio/ML library dependencies.

If you already use a managed Python environment, activate it and use `python -m pip`; do not mix packages from a different Python installation. Do not install into a shared/global environment to resolve a project-specific failure.

For the remaining `python` commands, activate your environment first or replace `python` with `.\.venv\Scripts\python.exe`.

## Alternative: Conda

The existing Conda definition provides a CPU-oriented environment:

```powershell
conda env create -f environment.yml
conda activate cqsentinel
python -m pip install --no-deps -e .
python -m cqsentinel.main
```

`environment.yml` supplies the dependencies; the editable install registers CQSentinel without asking pip to replace Conda-managed packages. The Python, Qt, PyTorch, and CTranslate2 bounds must stay consistent with `setup.py`. Neither definition is a complete, platform-specific lockfile; clean installation still needs release validation.

## Transcription and model setup

The application supports three explicit choices:

| Backend | Requirements | Audio destination |
| --- | --- | --- |
| Local Whisper | Local model files; sufficient RAM/CPU or compatible GPU | Local computer |
| Network Whisper | A separately configured compatible server | Configured server |
| OpenAI | `cloud` extra, explicit API key, and network access | OpenAI service; usage may be billed |

Models are not checked into this repository. Local setup downloads the selected model if it is absent; the current application uses `medium.en`. Prepare models before relying on offline operation. Configure backend settings before beginning a scan, and restart when prompted after changing them.

To enable the optional OpenAI backend in the active environment:

```powershell
python -m pip install -e ".[cloud]"
```

See [network transcription](docs/NETWORK_TRANSCRIPTION.md) and the [custom server documentation](docker/whisper-server/README.md) for the separate server setup. No server needs to be started to run the offline regression tests.

## Optional pitch detection and GPU configuration

The default pitch detector does not require CREPE. To install the optional CREPE/TensorFlow implementation in the active isolated environment:

```powershell
python -m pip install -e ".[gpu]"
```

The historical extra name `gpu` refers to these optional pitch packages; it does not select a CUDA-enabled PyTorch build. CUDA support depends on a compatible driver and PyTorch installation. Preserve the project's dependency bounds when configuring it. GPU performance, memory requirements, and auto-centering quality require measurement on the actual system.

## Radio and audio setup

Install Hamlib/rigctld for source operation, or use a build that includes it. In Settings, select the correct radio model, serial port, baud rate, and audio input. Connect and verify frequency/audio before scanning. Do not copy another user's COM port or model identifier without checking your device.

Scanning changes receiver frequency. Hardware test scripts and audio diagnostics can operate attached devices; review them before running. For development without hardware, use the offline suite below.

## Verify the development environment

```powershell
python -m pip check
python -B -m unittest discover -s tests -v
```

These checks do not certify a packaged executable or hardware compatibility. Before releasing a build, test on clean Windows without a development environment and exercise the intended radio/audio/backend combination.

If setup fails, capture the command, Python version, dependency error, and backend type. Avoid including `~/.cqsentinel/config.yaml`, API keys, personal recordings, or unredacted logs in a public report. Preserve existing configuration when diagnosing failures.
