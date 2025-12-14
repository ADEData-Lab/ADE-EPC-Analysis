"""Legacy London heat network analysis stub.

The previous implementation relied on a London-only GIS downloader that has been
archived under :mod:`src.legacy.acquisition`. This module is retained solely to
preserve history and now guards against accidental use.
"""

from textwrap import dedent

LEGACY_MESSAGE = dedent(
    """
    The London GIS download path has been retired and moved to src/legacy/acquisition.
    Heat network analysis for the national workflow should use the current spatial
    datasets documented in docs/GIS_DATA.md instead of this legacy helper.
    """
)


class HeatNetworkAnalyzer:
    """Placeholder that prevents usage of the legacy London-only workflow."""

    def __init__(self, *_, **__):
        raise RuntimeError(LEGACY_MESSAGE)
