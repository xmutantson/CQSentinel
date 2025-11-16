#!/usr/bin/env python3
"""
Build script for CQSentinel Windows executable

This script automates the build process using PyInstaller.

Usage:
    python scripts/build_windows.py [--onefile] [--clean]

Options:
    --onefile    Build single-file executable (slower startup)
    --clean      Clean build artifacts before building
"""

import sys
import os
import shutil
import subprocess
import argparse
from pathlib import Path


def clean_build():
    """Remove build artifacts"""
    print("🧹 Cleaning build artifacts...")

    dirs_to_remove = ['build', 'dist']
    files_to_remove = ['*.spec~']

    for dirname in dirs_to_remove:
        if os.path.exists(dirname):
            print(f"  Removing {dirname}/")
            shutil.rmtree(dirname)

    print("✓ Clean complete\n")


def check_dependencies():
    """Check if required tools are installed"""
    print("🔍 Checking dependencies...")

    required = {
        'PyInstaller': 'PyInstaller',
        'PyQt5': 'PyQt5',
    }

    missing = []

    for module, name in required.items():
        try:
            __import__(module.replace('-', '_'))
            print(f"  ✓ {name}")
        except ImportError:
            print(f"  ✗ {name} NOT FOUND")
            missing.append(name)

    if missing:
        print(f"\n❌ Missing dependencies: {', '.join(missing)}")
        print("Install with: pip install pyinstaller PyQt5")
        return False

    print("✓ All dependencies found\n")
    return True


def validate_native_extensions():
    """
    Validate that native extensions match the current Python version.

    This catches issues like tiktoken compiled for Python 3.11 but running in Python 3.10,
    which causes "Library not found: python311.dll" errors during PyInstaller analysis.
    """
    print("🔬 Validating native extension compatibility...")

    py_version = f"cp{sys.version_info.major}{sys.version_info.minor}"
    py_version_str = f"{sys.version_info.major}.{sys.version_info.minor}"

    print(f"  Python version: {py_version_str} (expecting {py_version} extensions)")

    # Packages with native extensions that must match Python version
    critical_packages = ['tiktoken', 'torch', 'numpy']

    import site
    search_dirs = []
    try:
        search_dirs.extend(site.getsitepackages())
    except Exception:
        pass
    search_dirs.extend(sys.path)

    errors = []

    for package in critical_packages:
        for search_dir in search_dirs:
            if not os.path.isdir(search_dir):
                continue

            package_dir = os.path.join(search_dir, package)
            if not os.path.isdir(package_dir):
                continue

            # Look for .pyd or .so files
            for fname in os.listdir(package_dir):
                if fname.endswith('.pyd') or (fname.endswith('.so') and 'cpython' in fname):
                    # Check if version tag matches
                    if 'cp3' in fname and py_version not in fname:
                        # Extract the actual version from filename
                        import re
                        match = re.search(r'cp(\d+)', fname)
                        if match:
                            ext_version = f"cp{match.group(1)}"
                            if ext_version != py_version:
                                errors.append(f"  ❌ {package}: {fname} is for Python {ext_version[2]}.{ext_version[3:]}, not {py_version_str}")
                                print(errors[-1])
                    else:
                        print(f"  ✓ {package}: {fname}")
            break  # Only check first found package directory

    if errors:
        print(f"\n❌ Native extension version mismatch detected!")
        print("This will cause PyInstaller to fail with 'Library not found: pythonXXX.dll' errors.")
        print("\nFix by reinstalling the mismatched packages:")
        print("  pip install --force-reinstall tiktoken")
        print("\nOr recreate the conda environment:")
        print("  conda env remove -n cqsentinel")
        print("  conda env create -f environment.yml")
        return False

    print("✓ All native extensions match Python version\n")
    return True


def check_hamlib():
    """Check if Hamlib is present, download if needed"""
    print("📡 Checking for Hamlib...")

    hamlib_dir = Path('external/hamlib')
    rigctld_path = hamlib_dir / 'bin' / 'rigctld.exe'

    if rigctld_path.exists():
        print(f"  ✓ Hamlib found at: {hamlib_dir}")
        print()
        return True

    print(f"  ⚠ Hamlib not found, downloading...")
    print()

    # Run download script
    download_script = Path(__file__).parent / 'download_hamlib.py'

    try:
        result = subprocess.run(
            [sys.executable, str(download_script)],
            check=True
        )

        if rigctld_path.exists():
            print()
            return True
        else:
            print("\n❌ Hamlib download failed")
            print("Please run: python scripts/download_hamlib.py")
            return False

    except subprocess.CalledProcessError as e:
        print(f"\n❌ Failed to download Hamlib: {e}")
        print("Please run: python scripts/download_hamlib.py")
        return False


def create_resources():
    """Create placeholder resources if they don't exist"""
    print("📦 Setting up resources...")

    resources_dir = Path('resources')
    resources_dir.mkdir(exist_ok=True)

    # Create placeholder icon if it doesn't exist
    icon_path = resources_dir / 'icon.ico'
    if not icon_path.exists():
        print("  ⚠ icon.ico not found, will build without custom icon")
    else:
        print(f"  ✓ Using icon: {icon_path}")

    print()


def build_executable(onefile=False):
    """Build the executable using PyInstaller"""

    spec_file = 'cqsentinel.spec'

    if onefile:
        print("🔨 Building single-file executable...")
        print("  Note: This will be slower to start but easier to distribute\n")
        # Modify spec file for onefile mode
        # For now, user needs to manually edit spec file
        print("  ⚠ For onefile mode, edit cqsentinel.spec and uncomment the onefile EXE section")
        return False
    else:
        print("🔨 Building directory-based executable...")
        print("  Note: This starts faster but creates a folder with multiple files\n")

    # Run PyInstaller
    cmd = ['pyinstaller', '--clean', spec_file]

    print(f"Running: {' '.join(cmd)}\n")

    try:
        result = subprocess.run(cmd, check=True)

        print("\n✅ Build successful!")
        print(f"\nExecutable location:")
        print(f"  dist/CQSentinel/CQSentinel.exe")

        # Check size
        exe_path = Path('dist/CQSentinel/CQSentinel.exe')
        if exe_path.exists():
            size_mb = exe_path.stat().st_size / (1024 * 1024)
            print(f"\nExecutable size: {size_mb:.1f} MB")

            # Count files in dist
            dist_files = list(Path('dist/CQSentinel').rglob('*'))
            print(f"Total files in distribution: {len(dist_files)}")

        return True

    except subprocess.CalledProcessError as e:
        print(f"\n❌ Build failed with error code {e.returncode}")
        return False


def create_zip():
    """Create a ZIP file of the distribution"""
    print("\n📦 Creating distribution ZIP...")

    dist_dir = Path('dist/CQSentinel')
    if not dist_dir.exists():
        print("  ⚠ dist/CQSentinel not found, skipping ZIP creation")
        return

    zip_name = 'CQSentinel-windows-portable'
    shutil.make_archive(zip_name, 'zip', 'dist', 'CQSentinel')

    zip_path = Path(f'{zip_name}.zip')
    if zip_path.exists():
        size_mb = zip_path.stat().st_size / (1024 * 1024)
        print(f"  ✓ Created {zip_path}")
        print(f"  Size: {size_mb:.1f} MB")


def main():
    parser = argparse.ArgumentParser(description='Build CQSentinel for Windows')
    parser.add_argument('--onefile', action='store_true',
                        help='Build single-file executable')
    parser.add_argument('--clean', action='store_true',
                        help='Clean build artifacts before building')
    parser.add_argument('--zip', action='store_true',
                        help='Create ZIP file of distribution')

    args = parser.parse_args()

    print("=" * 60)
    print("CQSentinel Windows Build Script")
    print("=" * 60)
    print()

    # Clean if requested
    if args.clean:
        clean_build()

    # Check dependencies
    if not check_dependencies():
        return 1

    # Validate native extensions match Python version
    if not validate_native_extensions():
        return 1

    # Check/download Hamlib
    if not check_hamlib():
        return 1

    # Create resources
    create_resources()

    # Build
    if not build_executable(onefile=args.onefile):
        return 1

    # Create ZIP if requested
    if args.zip:
        create_zip()

    print("\n" + "=" * 60)
    print("Build complete!")
    print("=" * 60)
    print("\nTo run:")
    print("  dist\\CQSentinel\\CQSentinel.exe")
    print("\nTo distribute:")
    print("  1. Copy entire dist/CQSentinel/ folder, or")
    print("  2. Use CQSentinel-windows-portable.zip, or")
    print("  3. Run scripts/build_installer.iss with Inno Setup")
    print()

    return 0


if __name__ == '__main__':
    sys.exit(main())
