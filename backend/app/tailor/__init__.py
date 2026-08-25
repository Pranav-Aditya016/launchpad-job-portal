"""Tailoring: CV/cover-letter generation and PDF rendering.

WeasyPrint imports its native GTK/Pango/Cairo stack at import time, and on a
machine missing those libs it raises OSError (not ImportError). Guard it HERE,
once: a failed submodule import is not cached in sys.modules, so every module
that retried this import would re-run WeasyPrint's failure and re-print its
stderr banner. Importers get `pdf` as either the module or None.
"""

try:
    from app.tailor import pdf
except OSError:
    pdf = None
