# PyInstaller runtime hook for tiktoken
# Fixes circular import error: "cannot import name '_tiktoken' from partially initialized module"
#
# The issue is that tiktoken/__init__.py imports from _tiktoken (native extension)
# during initialization. In PyInstaller frozen builds, this can cause a circular import
# because the native extension isn't fully loaded yet.
#
# This hook pre-imports the native extension before tiktoken is imported.

import sys
import importlib

def _preload_tiktoken_native():
    """
    Pre-load tiktoken's native Rust extension to avoid circular import.
    """
    try:
        # Try to import the native extension directly
        # This ensures it's loaded before tiktoken/__init__.py tries to import it
        if 'tiktoken._tiktoken' not in sys.modules:
            # Import the native module directly
            import tiktoken._tiktoken
    except ImportError as e:
        # If this fails, tiktoken won't work, but let the main code handle the error
        print(f"Warning: Could not pre-load tiktoken._tiktoken: {e}")
    except Exception as e:
        print(f"Warning: Error pre-loading tiktoken: {e}")

# Execute the preload
_preload_tiktoken_native()
