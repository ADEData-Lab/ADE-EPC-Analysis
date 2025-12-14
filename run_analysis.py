"""Deprecated interactive pipeline stub.

The previous London-focused acquisition workflow relied on modules that have
been archived under :mod:`src.legacy.acquisition`. This entry point now exits
immediately to avoid accidental use of deprecated downloaders and credentials.
"""

from textwrap import dedent

LEGACY_MESSAGE = dedent(
    """
    The interactive London download pipeline has been retired.

    EPC API and London GIS downloaders now live in src/legacy/acquisition for
    historical reference only and are no longer maintained. The national
    analysis workflow does not require these components; please use the current
    data preparation scripts instead of this launcher.
    """
)


def main() -> None:
    """Stop execution with a clear retirement notice."""
    raise SystemExit(LEGACY_MESSAGE)


if __name__ == "__main__":
    main()
