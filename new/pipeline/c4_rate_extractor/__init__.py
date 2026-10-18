"""Challenge C4: complete-file rate extraction and selection."""

__all__ = ["RateExtractor", "RateFileInput", "run_files"]


def __getattr__(name):
    if name in __all__:
        from . import rate_extractor
        return getattr(rate_extractor, name)
    raise AttributeError(name)
