# PyInstaller RUNTIME hook for tiktoken
#
# Fixes circular import: "cannot import name '_tiktoken' from partially initialized module"
#
# ROOT CAUSE: tiktoken/core.py uses ABSOLUTE import `from tiktoken import _tiktoken`
# In PyInstaller's FrozenImporter, when tiktoken package is being initialized and core.py
# tries this absolute import, Python sees tiktoken is already initializing → circular import.
#
# SOLUTION: Install an import hook that intercepts `from tiktoken import _tiktoken`
# and loads the native extension directly, bypassing the package initialization check.

import sys
import importlib.abc
import importlib.machinery
import importlib.util


class TiktokenImportFixer(importlib.abc.MetaPathFinder):
    """
    Import hook that fixes tiktoken's circular import in PyInstaller frozen builds.

    When tiktoken/core.py does `from tiktoken import _tiktoken`, this hook intercepts
    the import and loads the native extension directly without triggering package re-init.
    """

    def find_module(self, fullname, path=None):
        # Only intercept tiktoken._tiktoken imports
        if fullname == 'tiktoken._tiktoken':
            return self
        return None

    def load_module(self, fullname):
        if fullname in sys.modules:
            return sys.modules[fullname]

        if fullname != 'tiktoken._tiktoken':
            raise ImportError(f"Cannot load {fullname}")

        # Find and load the native extension directly
        try:
            import os

            # Get PyInstaller's base path
            if hasattr(sys, '_MEIPASS'):
                base_path = sys._MEIPASS
            else:
                base_path = os.path.dirname(sys.executable)

            # Search for the native extension file
            tiktoken_dir = os.path.join(base_path, 'tiktoken')
            ext_path = None

            if os.path.isdir(tiktoken_dir):
                for fname in os.listdir(tiktoken_dir):
                    if fname.startswith('_tiktoken') and not fname.endswith('.py'):
                        ext_path = os.path.join(tiktoken_dir, fname)
                        break

            if ext_path is None:
                raise ImportError(f"Could not find tiktoken._tiktoken native extension in {tiktoken_dir}")

            # Load using ExtensionFileLoader
            loader = importlib.machinery.ExtensionFileLoader(fullname, ext_path)
            spec = importlib.util.spec_from_file_location(
                fullname, ext_path, loader=loader
            )

            if spec is None:
                raise ImportError(f"Could not create spec for {ext_path}")

            module = importlib.util.module_from_spec(spec)
            sys.modules[fullname] = module
            spec.loader.exec_module(module)

            return module

        except Exception as e:
            # Clean up on failure
            sys.modules.pop(fullname, None)
            raise ImportError(f"Failed to load tiktoken._tiktoken: {e}") from e


# Only install hook in frozen PyInstaller builds
if getattr(sys, 'frozen', False):
    # Install our import hook at the FRONT of meta_path
    # This ensures it gets first crack at importing tiktoken._tiktoken
    sys.meta_path.insert(0, TiktokenImportFixer())
