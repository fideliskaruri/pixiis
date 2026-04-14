"""Setup script for transcriptions package."""
from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="transcriptions",
    version="0.1.0",
    author="Your Name",
    description="A lightweight transcription helper library for Whisper models",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/transcriptions",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
    install_requires=[
        "faster-whisper",
        "numpy",
        "scipy",
        "sounddevice",
        "soundfile",
    ],
    extras_require={
        "dev": [
            "pytest",
            "pytest-cov",
            "black",
            "flake8",
        ],
    },
)
