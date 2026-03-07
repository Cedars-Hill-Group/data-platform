"""
data-platform
=============
Data access, normalization, and storage abstractions for the CHG Operating System.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("data-platform")
except PackageNotFoundError:
    __version__ = "0.1.0"

__all__ = ["__version__"]
