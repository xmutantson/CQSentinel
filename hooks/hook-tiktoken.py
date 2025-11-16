# PyInstaller runtime hook for tiktoken
# Fixes circular import error: "cannot import name '_tiktoken' from partially initialized module"
#
# The issue is that tiktoken/__init__.py imports from _tiktoken (native extension)
# during initialization. In PyInstaller frozen builds, this can cause a circular import
# because the native extension isn't fully loaded yet.
#
# This hook pre-imports the native extension before tiktoken is imported.

import sys
import os

def _preload_tiktoken_native():
    """
    Pre-load tiktoken's native Rust extension to avoid circular import.

    The issue: When we use importlib.util.find_spec('tiktoken._tiktoken'), Python's
    import machinery still tries to initialize the parent 'tiktoken' package first,
    which runs tiktoken/__init__.py, which tries to import _tiktoken - circular import.

    Solution: Directly locate and load the .pyd/.so file using ExtensionFileLoader
    without going through the import system at all. This bypasses parent package
    initialization entirely.
    """
    if 'tiktoken._tiktoken' in sys.modules:
        # Already loaded, nothing to do
        return

    # Only run in frozen (PyInstaller) environment
    if not getattr(sys, 'frozen', False):
        return

    try:
        # Get the base path where PyInstaller extracts files
        if hasattr(sys, '_MEIPASS'):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.dirname(sys.executable)

        # Find the native extension file directly in the filesystem
        # PyInstaller places it as tiktoken/_tiktoken.{ext} or _tiktoken.{ext}
        ext_suffixes = ['.pyd', '.so', '.cpython-310-x86_64-linux-gnu.so']

        # Also check for version-specific suffixes
        if sys.version_info[:2] == (3, 10):
            ext_suffixes.extend([
                '.cp310-win_amd64.pyd',
                '.cpython-310-x86_64-linux-gnu.so',
            ])

        tiktoken_ext_path = None

        # Search in tiktoken subdirectory first (PyInstaller usually puts it here)
        tiktoken_dir = os.path.join(base_path, 'tiktoken')
        if os.path.isdir(tiktoken_dir):
            for suffix in ext_suffixes:
                candidate = os.path.join(tiktoken_dir, f'_tiktoken{suffix}')
                if os.path.isfile(candidate):
                    tiktoken_ext_path = candidate
                    break

        # Also check base path (some PyInstaller configs put extensions at root)
        if tiktoken_ext_path is None:
            for suffix in ext_suffixes:
                candidate = os.path.join(base_path, f'_tiktoken{suffix}')
                if os.path.isfile(candidate):
                    tiktoken_ext_path = candidate
                    break

        if tiktoken_ext_path is None:
            # Last resort: scan tiktoken directory for any _tiktoken.* file
            if os.path.isdir(tiktoken_dir):
                for fname in os.listdir(tiktoken_dir):
                    if fname.startswith('_tiktoken.') and not fname.endswith('.py'):
                        tiktoken_ext_path = os.path.join(tiktoken_dir, fname)
                        break

        if tiktoken_ext_path is None:
            print("Warning: Could not find tiktoken._tiktoken native extension file")
            return

        # Load the extension module directly using ExtensionFileLoader
        # This bypasses the import system entirely, avoiding parent package init
        import importlib.machinery
        import importlib.util

        loader = importlib.machinery.ExtensionFileLoader('tiktoken._tiktoken', tiktoken_ext_path)
        spec = importlib.util.spec_from_file_location(
            'tiktoken._tiktoken',
            tiktoken_ext_path,
            loader=loader,
            submodule_search_locations=[]
        )

        if spec is None:
            print(f"Warning: Could not create spec for {tiktoken_ext_path}")
            return

        # Create the module object
        module = importlib.util.module_from_spec(spec)

        # CRITICAL: Add to sys.modules BEFORE executing
        # This ensures that when tiktoken/__init__.py runs and tries to import
        # _tiktoken, it finds our pre-loaded module in sys.modules
        sys.modules['tiktoken._tiktoken'] = module

        # Execute/load the native extension
        spec.loader.exec_module(module)

    except Exception as e:
        # Clean up on failure
        sys.modules.pop('tiktoken._tiktoken', None)
        print(f"Warning: Could not pre-load tiktoken._tiktoken: {e}")

# Execute the preload
_preload_tiktoken_native()
