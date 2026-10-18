"""Challenge C3: File Quality & Completeness Grading Engine
Calculates defensible quality metrics and assigns a Composite File Quality Score (FQS) to PTD rate files.
"""
__all__ = ["FileQualityGrader"]


def __getattr__(name):
    if name == "FileQualityGrader":
        from .file_grader import FileQualityGrader
        return FileQualityGrader
    raise AttributeError(name)
