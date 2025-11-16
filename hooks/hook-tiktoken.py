# PyInstaller ANALYSIS hook for tiktoken
#
# This hook runs during PyInstaller's analysis phase to ensure all tiktoken
# submodules and data files are properly included in the bundle.
#
# NOTE: This is an ANALYSIS hook, not a runtime hook. Runtime hooks should
# be in rthook-*.py files and specified in runtime_hooks in the spec file.

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs
import os
import sys
import site

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
# NOTE: collect_dynamic_libs() may not find the .pyd/.so because it can't
# import tiktoken due to circular import. We search manually below.
binaries = collect_dynamic_libs('tiktoken')

# CRITICAL: Explicitly find and add the native extension
# collect_dynamic_libs may fail due to circular import issues
search_dirs = []
try:
    search_dirs.extend(site.getsitepackages())
except Exception:
    pass
try:
    search_dirs.append(site.getusersitepackages())
except Exception:
    pass
search_dirs.extend(sys.path)

tiktoken_found = False
for search_dir in search_dirs:
    if not os.path.isdir(search_dir):
        continue
    tiktoken_dir = os.path.join(search_dir, 'tiktoken')
    if os.path.isdir(tiktoken_dir):
        for fname in os.listdir(tiktoken_dir):
            if fname.startswith('_tiktoken') and (fname.endswith('.pyd') or fname.endswith('.so')):
                ext_path = os.path.join(tiktoken_dir, fname)
                # Add as (source, dest_folder)
                binaries.append((ext_path, 'tiktoken'))
                print(f"hook-tiktoken: Found native extension: {ext_path}")
                tiktoken_found = True
                break
        if tiktoken_found:
            break

if not tiktoken_found:
    print("hook-tiktoken: WARNING - Native extension (.pyd/.so) not found!")
