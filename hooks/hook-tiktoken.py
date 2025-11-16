# PyInstaller runtime hook for tiktoken
# Fixes circular import error: "cannot import name '_tiktoken' from partially initialized module"
#
# The issue is that tiktoken/__init__.py imports from _tiktoken (native extension)
# during initialization. In PyInstaller frozen builds, this can cause a circular import
# because the native extension isn't fully loaded yet.
#
# This hook pre-imports the native extension before tiktoken is imported.

import sys
import importlib.util

def _preload_tiktoken_native():
    """
    Pre-load tiktoken's native Rust extension to avoid circular import.

    The issue: When we do 'import tiktoken._tiktoken', Python first initializes
    the parent package 'tiktoken' (runs tiktoken/__init__.py), which itself tries
    to import _tiktoken, causing a circular import.

    Solution: Use importlib.util to load the native extension directly without
    triggering the parent package initialization.
    """
    if 'tiktoken._tiktoken' in sys.modules:
        # Already loaded, nothing to do
        return

    try:
        # Find the native extension module spec
        spec = importlib.util.find_spec('tiktoken._tiktoken')
        if spec is None:
            print("Warning: Could not find tiktoken._tiktoken module spec")
            return

        # Create the module from spec without importing the parent
        module = importlib.util.module_from_spec(spec)

        # Add to sys.modules BEFORE executing to handle any internal imports
        sys.modules['tiktoken._tiktoken'] = module

        # Execute the module (loads the native extension)
        if spec.loader is not None:
            spec.loader.exec_module(module)

    except ImportError as e:
        # If this fails, tiktoken won't work, but let the main code handle the error
        # Remove from sys.modules if we added it but failed to load
        sys.modules.pop('tiktoken._tiktoken', None)
        print(f"Warning: Could not pre-load tiktoken._tiktoken: {e}")
    except Exception as e:
        sys.modules.pop('tiktoken._tiktoken', None)
        print(f"Warning: Error pre-loading tiktoken: {e}")

# Execute the preload
_preload_tiktoken_native()
