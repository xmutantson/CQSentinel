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
        'pyinstaller': 'PyInstaller',
        'PyQt6': 'PyQt6',
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
        print("Install with: pip install pyinstaller PyQt6")
        return False

    print("✓ All dependencies found\n")
    return True


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
