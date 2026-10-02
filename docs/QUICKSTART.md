# CQSentinel quick start

CQSentinel is a development preview. Start with the current [installation guide](../INSTALL.md); older phase documents are historical design notes.

## Configure one receiving workflow

1. Start `python -m cqsentinel.main` from your isolated environment.
2. Open Settings and select your radio, serial connection, audio input, and transcription backend.
3. For local transcription, make the required model available before an offline session. For network or cloud transcription, configure that backend explicitly. Restart if a changed setting requires it.
4. Connect the radio and verify the displayed frequency and audio level.
5. Choose the bands to scan and click **Start Scan**.
6. Review station callsigns and transcripts on the band map. Recognition can be wrong; confirm before using it for a contact or log entry.
7. Use **Skip** to abandon the current signal. Use **Stop Scan** and wait for stopping to finish before retuning manually, restarting, or changing devices.

The scanner controls the connected receiver. It cannot simultaneously leave that same receiver under independent manual tuning control. Voice fingerprinting is disabled; it is not a reliable way to identify a worked station in this version.

## Offline development checks

From the repository root:

```powershell
python -B -m unittest discover -s tests -v
```

The regression suite substitutes radio, network, and inference boundaries. It needs no connected receiver, running rigctld, downloaded speech model, API key, or transcription server. Do not replace it with `scripts/test/` hardware utilities when checking a routine code change.

## Before field use

- Verify the exact radio/audio/backend combination in a controlled session.
- Exercise stop and restart, device disconnection, and transcription failure.
- Check that transcripts remain associated with their capture frequency.
- Prepare local model files if internet access will be unavailable.
- Keep configuration and any configured API key private.

See [README](../README.md) for current scope and limitations, [BUILD](../BUILD.md) for packaging, and [network transcription](NETWORK_TRANSCRIPTION.md) for server setup. Passing offline tests is not hardware or packaged-release acceptance.
