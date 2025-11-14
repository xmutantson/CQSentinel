"""
Download and prepare Hamlib for bundling with CQSentinel

This script downloads the latest Hamlib Windows binaries and prepares
them for inclusion in the PyInstaller build.
"""

import os
import sys
import zipfile
import urllib.request
import shutil
from pathlib import Path

# Hamlib version and download URL
HAMLIB_VERSION = "4.5.5"
HAMLIB_URL = f"https://github.com/Hamlib/Hamlib/releases/download/{HAMLIB_VERSION}/hamlib-w64-{HAMLIB_VERSION}.zip"

def download_hamlib(dest_dir: Path):
    """
    Download Hamlib Windows binaries

    Args:
        dest_dir: Destination directory for Hamlib files
    """
    print(f"Downloading Hamlib {HAMLIB_VERSION}...")
    print(f"URL: {HAMLIB_URL}")

    # Create temp directory
    temp_dir = dest_dir / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    # Download zip file
    zip_path = temp_dir / f"hamlib-{HAMLIB_VERSION}.zip"

    try:
        with urllib.request.urlopen(HAMLIB_URL) as response:
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0

            with open(zip_path, 'wb') as f:
                while True:
                    chunk = response.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)

                    if total_size > 0:
                        percent = (downloaded / total_size) * 100
                        print(f"\rDownload progress: {percent:.1f}%", end='')

        print("\nDownload complete!")

    except Exception as e:
        print(f"\nError downloading Hamlib: {e}")
        print("\nPlease download manually from:")
        print(f"  {HAMLIB_URL}")
        print(f"Extract to: {dest_dir}")
        return False

    # Extract zip file
    print("Extracting Hamlib...")
    hamlib_dir = dest_dir / "hamlib"
    hamlib_dir.mkdir(exist_ok=True)

    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(temp_dir)

    # Find the extracted directory (it has a version-specific name)
    extracted_dirs = [d for d in temp_dir.iterdir() if d.is_dir()]
    if not extracted_dirs:
        print("Error: Could not find extracted directory")
        return False

    extracted_dir = extracted_dirs[0]

    # Copy bin directory to hamlib directory
    bin_src = extracted_dir / "bin"
    if bin_src.exists():
        bin_dest = hamlib_dir / "bin"
        if bin_dest.exists():
            shutil.rmtree(bin_dest)
        shutil.copytree(bin_src, bin_dest)
        print(f"Copied binaries to {bin_dest}")
    else:
        print(f"Warning: bin directory not found in {extracted_dir}")

    # Copy lib directory (for DLLs)
    lib_src = extracted_dir / "lib"
    if lib_src.exists():
        lib_dest = hamlib_dir / "lib"
        if lib_dest.exists():
            shutil.rmtree(lib_dest)
        shutil.copytree(lib_src, lib_dest)
        print(f"Copied libraries to {lib_dest}")

    # Clean up temp directory
    shutil.rmtree(temp_dir)
    print("Cleanup complete!")

    # Verify rigctld.exe exists
    rigctld_path = hamlib_dir / "bin" / "rigctld.exe"
    if rigctld_path.exists():
        print(f"\n✓ rigctld.exe found at: {rigctld_path}")
        return True
    else:
        print(f"\n✗ rigctld.exe NOT found!")
        return False


def main():
    """Main entry point"""

    # Get the project root directory
    script_dir = Path(__file__).parent
    project_root = script_dir.parent

    # Create external directory for Hamlib
    external_dir = project_root / "external"
    external_dir.mkdir(exist_ok=True)

    print("=" * 60)
    print("CQSentinel Hamlib Download Script")
    print("=" * 60)
    print()

    # Check if Hamlib is already downloaded
    hamlib_dir = external_dir / "hamlib"
    rigctld_path = hamlib_dir / "bin" / "rigctld.exe"

    if rigctld_path.exists():
        print(f"Hamlib already exists at: {hamlib_dir}")
        response = input("Re-download? (y/N): ").strip().lower()
        if response != 'y':
            print("Using existing Hamlib installation.")
            return 0

    # Download and extract Hamlib
    success = download_hamlib(external_dir)

    if success:
        print("\n" + "=" * 60)
        print("SUCCESS! Hamlib is ready for bundling.")
        print("=" * 60)
        print()
        print("Next steps:")
        print("1. Run: python scripts/build_windows.py")
        print("2. Hamlib will be automatically included in the .exe")
        print()
        return 0
    else:
        print("\n" + "=" * 60)
        print("FAILED to download Hamlib.")
        print("=" * 60)
        print()
        print("Please download manually and extract to:")
        print(f"  {external_dir / 'hamlib'}")
        print()
        return 1


if __name__ == '__main__':
    sys.exit(main())
