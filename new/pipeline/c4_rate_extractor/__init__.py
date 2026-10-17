"""Challenge C4: Streaming Rate Extraction & Multi-Rate Conflict Resolution Engine
Extracts provider-level rates from large CMS TiC JSON files and resolves multi-rate conflicts.
"""
from .rate_extractor import RateExtractor

__all__ = ["RateExtractor"]
