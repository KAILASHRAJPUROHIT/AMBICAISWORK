"""FLUX.2 fine-tuning dataset tooling — builds a manifest-driven training
set from approved, company-owned before/after image pairs. Kept separate
from the live catalogue pipeline (app.py etc.): this package is offline
dataset preparation, never called from a request handler.
"""
