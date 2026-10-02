"""Load real core modules without importing GUI/audio-device package initializers.

Inference and tuner dependencies are explicit stubs. No test in this fixture
constructs a device, downloads a model, or connects to a service.
"""
import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name, relative_path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


for package in ('offline_cq', 'offline_cq.bandmap', 'offline_cq.scanner',
                'offline_cq.signal', 'offline_cq.radio'):
    module = types.ModuleType(package)
    module.__path__ = []
    sys.modules[package] = module

station = load('offline_cq.bandmap.station', 'cqsentinel/bandmap/station.py')
sys.modules['offline_cq.bandmap'].StationStatus = station.StationStatus
sys.modules['offline_cq.bandmap'].ActivityType = station.ActivityType
engine = load('offline_cq.scanner.engine', 'cqsentinel/scanner/engine.py')
load('offline_cq.scanner.profiles', 'cqsentinel/scanner/profiles.py')
carrier = load('offline_cq.signal.carrier_detector', 'cqsentinel/signal/carrier_detector.py')
analysis = load('offline_cq.signal.transcript_analyzer', 'cqsentinel/signal/transcript_analyzer.py')
recording = load('offline_cq.signal.recording_session', 'cqsentinel/signal/recording_session.py')

for module_name, class_name in (('auto_tuner', 'SSBAutoTuner'), ('fm_tuner', 'FMAutoTuner'),
                                ('pitch', 'PitchDetector')):
    module = types.ModuleType('offline_cq.radio.' + module_name)
    setattr(module, class_name, type(class_name, (), {}))
    sys.modules[module.__name__] = module
signals = load('offline_cq.signal.signal_scanner', 'cqsentinel/signal/signal_scanner.py')
