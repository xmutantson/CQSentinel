# PyInstaller hook for tiktoken
# Ensures proper bundling of tiktoken with its native Rust extension

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

# Collect all tiktoken submodules
hiddenimports = collect_submodules('tiktoken')

# Add tiktoken_ext which contains the encoding definitions
hiddenimports += collect_submodules('tiktoken_ext')

# Explicitly add the native extension
hiddenimports += ['tiktoken._tiktoken']

# Collect all data files (encoding files, etc.)
datas = collect_data_files('tiktoken')
datas += collect_data_files('tiktoken_ext')

# Collect native binaries (.pyd on Windows, .so on Linux)
binaries = collect_dynamic_libs('tiktoken')

# Print what we collected for debugging
print(f"tiktoken hook: collected {len(hiddenimports)} hidden imports")
print(f"tiktoken hook: collected {len(datas)} data files")
print(f"tiktoken hook: collected {len(binaries)} binaries")
