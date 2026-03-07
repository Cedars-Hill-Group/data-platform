"""
data-platform
=============
Data access, normalization, and storage abstractions for the CHG Operating System.
"""

from importlib.metadata import PackageNotFoundError, version

from data_platform.log import configure_logging, get_logger

try:
    __version__ = version("data-platform")
except PackageNotFoundError:
    __version__ = "0.1.0"

__all__ = ["__version__", "configure_logging", "get_logger"]
