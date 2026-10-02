#!/usr/bin/env python3
"""
CQSentinel Setup Script
"""

from setuptools import setup, find_packages
import os

# Read the README for long description
def read_file(filename):
    filepath = os.path.join(os.path.dirname(__file__), filename)
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    return ''

setup(
    name='cqsentinel',
    version='0.1.0',
    description='SSB contest band scanner with speech transcription',
    long_description=read_file('README.md'),
    long_description_content_type='text/markdown',
    author='CQSentinel Development Team',
    author_email='',
    url='https://github.com/xmutantson/CQSentinel',
    license='TBD',

    packages=find_packages(exclude=['tests', 'tests.*']),

    python_requires='>=3.10',

    install_requires=[
        'PyQt5>=5.15.0',
        'sounddevice>=0.4.6',
        'soundfile>=0.12.1',
        'noisereduce>=3.0.0',
        'torch>=2.0.0,<2.6.0',
        'torchaudio>=2.0.0,<2.6.0',
        'silero-vad>=4.0.0',
        'faster-whisper>=0.10.0',
        'ctranslate2<4.5.0',
        'openai-whisper>=20230314',
        'librosa>=0.10.0',
        'resampy>=0.4.2',
        # Note: resemblyzer removed - not effective for SSB audio
        'numpy>=1.24.0',
        'scipy>=1.10.0',
        'scikit-learn>=1.3.0',
        'pyserial>=3.5',
        'requests>=2.31.0',
        'pyyaml>=6.0',
        'colorlog>=6.7.0',
        'tqdm>=4.65.0',
        "pywin32>=306; sys_platform == 'win32'",
    ],

    extras_require={
        'cloud': [
            'openai>=1.0.0',
        ],
        'dev': [
            'pytest>=7.4.0',
            'pytest-qt>=4.2.0',
            'pytest-cov>=4.1.0',
            'black>=23.0.0',
            'flake8>=6.0.0',
            'mypy>=1.4.0',
        ],
        'gpu': [
            'crepe>=0.0.12',
            'tensorflow>=2.10.0,<2.18.0',
        ],
        'build': [
            'pyinstaller>=5.13.0',
            'pyinstaller-hooks-contrib>=2023.6',
        ],
        'advanced': [
            'pyannote-audio>=3.0.0',
        ],
    },

    entry_points={
        'console_scripts': [
            'cqsentinel=cqsentinel.main:main',
        ],
    },

    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: End Users/Desktop',
        'Topic :: Communications :: Ham Radio',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Operating System :: Microsoft :: Windows',
        'Operating System :: POSIX :: Linux',
    ],

    keywords='ham radio amateur radio contesting ssb voice recognition ai',

    package_data={
        'cqsentinel': [
            'resources/*.png',
            'resources/*.ico',
            'contest_profiles/*.json',
        ],
    },

    include_package_data=True,
)
