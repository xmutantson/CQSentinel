#!/usr/bin/env python3
"""
Check which package is pulling in the obsolete 'typing' package.
"""
import subprocess
import sys
import json

def check_typing_dependency():
    """Find which package depends on the obsolete 'typing' package."""

    print("Checking which package depends on 'typing'...\n")

    # Get list of all installed packages
    result = subprocess.run(
        [sys.executable, '-m', 'pip', 'list', '--format=json'],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print("Error getting package list")
        return

    packages = json.loads(result.stdout)

    # Check if typing is installed
    typing_found = False
    for pkg in packages:
        if pkg['name'] == 'typing':
            typing_found = True
            print(f"✗ Found obsolete 'typing' package version {pkg['version']}")
            break

    if not typing_found:
        print("✓ No obsolete 'typing' package found!")
        return

    print("\nChecking dependencies of pip packages...\n")

    # Get the pip packages from environment.yml
    pip_packages = [
        'faster-whisper',
        'resemblyzer',
        'noisereduce',
        'silero-vad',
        'openai-whisper',
        'pyinstaller-hooks-contrib',
        'pytest-qt',
        'pytest-cov'
    ]

    culprits = []

    for pkg_name in pip_packages:
        # Get package info
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'show', pkg_name],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            continue

        # Parse the output
        lines = result.stdout.split('\n')
        for line in lines:
            if line.startswith('Requires:'):
                deps = line.replace('Requires:', '').strip()
                if deps and 'typing' in deps.lower():
                    print(f"⚠ {pkg_name}")
                    print(f"  Requires: {deps}")
                    culprits.append((pkg_name, deps))
                    print()

    if culprits:
        print("\n" + "="*60)
        print("CULPRIT(S) FOUND:")
        print("="*60)
        for pkg, deps in culprits:
            print(f"Package: {pkg}")
            print(f"Dependencies: {deps}")
            print()

        print("These packages incorrectly list 'typing' as a dependency,")
        print("even though Python 3.5+ has it built-in.")
        print("\nSolution: pip uninstall typing -y")
    else:
        print("No packages explicitly list 'typing' as a dependency.")
        print("It may be a transitive dependency (dependency of a dependency).")
        print("\nTo find it, run:")
        print("  pip install pipdeptree")
        print("  pipdeptree --reverse --packages typing")

if __name__ == '__main__':
    check_typing_dependency()
