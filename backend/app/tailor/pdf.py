from pathlib import Path
from markdown import markdown as md_to_html   # add "markdown" to deps
from weasyprint import HTML
from app import config as cfg

_TEMPLATE = (Path(__file__).parent / "cv_template.html").read_text(encoding="utf-8")

def render_cv_pdf(doc, out_path: Path) -> Path:
    body = md_to_html(doc.cv_markdown)
    html = _TEMPLATE.replace("{{ body }}", body)
    HTML(string=html).write_pdf(str(out_path))
    return out_path
