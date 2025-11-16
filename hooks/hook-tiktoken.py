# PyInstaller ANALYSIS hook for tiktoken
#
# This hook runs during PyInstaller's analysis phase to ensure all tiktoken
# submodules and data files are properly included in the bundle.
#
# NOTE: This is an ANALYSIS hook, not a runtime hook. Runtime hooks should
# be in rthook-*.py files and specified in runtime_hooks in the spec file.

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

# Explicitly list all tiktoken submodules since collect_submodules() fails
# due to circular import issues in tiktoken's package structure
hiddenimports = [
    'tiktoken',
    'tiktoken._tiktoken',  # Native Rust extension
    'tiktoken.core',
    'tiktoken.load',
    'tiktoken.model',
    'tiktoken.registry',
    'tiktoken_ext',
    'tiktoken_ext.openai_public',
]

# Collect data files (encoding files like cl100k_base.tiktoken)
datas = collect_data_files('tiktoken')
datas += collect_data_files('tiktoken_ext')

# Collect native extension libraries
binaries = collect_dynamic_libs('tiktoken')
