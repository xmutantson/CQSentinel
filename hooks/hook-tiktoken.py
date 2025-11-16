# PyInstaller runtime hook for tiktoken
#
# NOTE: This hook is intentionally empty. Previous attempts to "pre-load" tiktoken._tiktoken
# using `import tiktoken._tiktoken` CAUSED the circular import error, they didn't fix it.
#
# The circular import happens because:
# 1. `import tiktoken._tiktoken` triggers tiktoken package initialization
# 2. tiktoken/__init__.py imports from .core
# 3. tiktoken/core.py does `from tiktoken import _tiktoken` (absolute import)
# 4. Python sees tiktoken is already being initialized → circular import
#
# The solution is to NOT pre-import anything. Just let Python's import system handle it
# naturally when whisper imports tiktoken. The hidden imports in cqsentinel.spec ensure
# all necessary modules are bundled.
#
# If tiktoken still fails to load, the issue is with PyInstaller bundling, not import order.
pass
