from pathlib import Path

import pytest

# WeasyPrint imports its native GTK/Pango/Cairo stack at import time. On
# machines missing those native libs (e.g. Windows without the GTK runtime),
# `import weasyprint` raises OSError rather than ImportError, so it must be
# passed explicitly via exc_type for importorskip to actually skip instead of
# erroring out the suite.
pytest.importorskip("weasyprint", exc_type=OSError)

from app.tailor import pdf
from app.models import TailoredDoc

def test_render_pdf(tmp_path):
    out = tmp_path / "cv.pdf"
    p = pdf.render_cv_pdf(TailoredDoc(job_id="j1",
        cv_markdown="# Ann Lee\n\n**ML Engineer**\n\n- Built X", cover_letter="Hi"), out)
    assert p.exists() and p.stat().st_size > 500
    assert p.read_bytes()[:4] == b"%PDF"
