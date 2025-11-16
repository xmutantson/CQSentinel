# PyInstaller ANALYSIS hook for openai-whisper
#
# This hook runs during PyInstaller's analysis phase to ensure all whisper
# submodules and data files are properly included in the bundle.
#
# NOTE: collect_submodules('whisper') fails because importing whisper triggers
# tiktoken import which has circular import issues. We explicitly list modules.

from PyInstaller.utils.hooks import collect_data_files

# Explicitly list all whisper submodules since collect_submodules() fails
# due to tiktoken circular import issues
hiddenimports = [
    'whisper',
    'whisper.audio',
    'whisper.decoding',
    'whisper.model',
    'whisper.normalizers',
    'whisper.timing',
    'whisper.tokenizer',
    'whisper.transcribe',
    'whisper.utils',
]

# Collect data files (mel filters, model assets, etc.)
datas = collect_data_files('whisper')
