"""
PDF Report Generator
Converts Markdown equity research reports to styled PDFs.

Usage:
    python tools/pdf_gen.py --input output/AAPL_initiation_2026-03-10.md --output output/AAPL_initiation_2026-03-10.pdf
    python tools/pdf_gen.py --input output/report.md --output output/report.pdf --theme dark

Dependencies: weasyprint, markdown
Install: pip install weasyprint markdown --break-system-packages
"""

import argparse
import re
import sys
from pathlib import Path

try:
    import markdown
except ImportError:
    print("ERROR: markdown not installed. Run: pip install markdown --break-system-packages")
    sys.exit(1)

try:
    from weasyprint import HTML
except ImportError:
    # Fallback: try using pandoc
    HTML = None
    print("WARNING: weasyprint not available. Will try pandoc fallback.")


# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------

CSS_LIGHT = """
@page {
    size: letter;
    margin: 0.75in 0.85in;
    @top-right {
        content: "EQUITY RESEARCH";
        font-family: 'Helvetica Neue', Arial, sans-serif;
        font-size: 8pt;
        color: #999999;
    }
    @bottom-center {
        content: counter(page) " / " counter(pages);
        font-family: 'Helvetica Neue', Arial, sans-serif;
        font-size: 8pt;
        color: #999999;
    }
}

body {
    font-family: 'Helvetica Neue', Arial, sans-serif;
    font-size: 10.5pt;
    line-height: 1.55;
    color: #1a1a1a;
    max-width: 100%;
}

h1 {
    font-size: 20pt;
    font-weight: 700;
    color: #1B4F72;
    border-bottom: 2.5px solid #1B4F72;
    padding-bottom: 8px;
    margin-top: 0;
    margin-bottom: 16px;
}

h2 {
    font-size: 14pt;
    font-weight: 700;
    color: #1B4F72;
    border-bottom: 1px solid #D5E8F0;
    padding-bottom: 4px;
    margin-top: 28px;
    margin-bottom: 12px;
    page-break-after: avoid;
}

h3 {
    font-size: 11.5pt;
    font-weight: 700;
    color: #2E75B6;
    margin-top: 18px;
    margin-bottom: 8px;
    page-break-after: avoid;
}

p {
    margin-bottom: 8px;
    text-align: justify;
}

strong {
    color: #1a1a1a;
}

/* Tables */
table {
    width: 100%;
    border-collapse: collapse;
    margin: 14px 0;
    font-size: 9.5pt;
    page-break-inside: avoid;
}

thead th {
    background-color: #1B4F72;
    color: white;
    font-weight: 600;
    padding: 8px 10px;
    text-align: left;
    border: none;
}

tbody td {
    padding: 6px 10px;
    border-bottom: 1px solid #E8E8E8;
}

tbody tr:nth-child(even) {
    background-color: #F8FAFB;
}

tbody tr:hover {
    background-color: #EDF4F8;
}

/* Code blocks (for tags, mermaid placeholders) */
pre {
    background-color: #F5F7FA;
    border: 1px solid #E0E4E8;
    border-radius: 4px;
    padding: 12px 16px;
    font-size: 9pt;
    overflow-x: auto;
    page-break-inside: avoid;
}

code {
    font-family: 'SF Mono', 'Consolas', 'Monaco', monospace;
    font-size: 9pt;
    background-color: #F0F2F5;
    padding: 1px 4px;
    border-radius: 3px;
}

/* Lists */
ul, ol {
    margin-bottom: 10px;
    padding-left: 24px;
}

li {
    margin-bottom: 4px;
}

/* Block quotes (for notes/callouts) */
blockquote {
    border-left: 3px solid #2E86C1;
    padding: 8px 16px;
    margin: 12px 0;
    background-color: #F0F7FC;
    color: #333;
    font-style: normal;
}

/* Images (charts) */
img {
    max-width: 100%;
    height: auto;
    display: block;
    margin: 14px auto;
    page-break-inside: avoid;
}

/* Horizontal rules */
hr {
    border: none;
    border-top: 1px solid #D0D4D8;
    margin: 20px 0;
}

/* Executive summary highlight */
h2 + ul {
    background-color: #F0F7FC;
    border-left: 3px solid #1B4F72;
    padding: 12px 20px;
    border-radius: 0 4px 4px 0;
    list-style-type: none;
}

h2 + ul li {
    padding: 4px 0;
}

h2 + ul li::before {
    content: "▸ ";
    color: #1B4F72;
    font-weight: bold;
}

/* Print-specific */
@media print {
    h2 { page-break-after: avoid; }
    table { page-break-inside: avoid; }
    .no-break { page-break-inside: avoid; }
}
"""

CSS_DARK = """
@page {
    size: letter;
    margin: 0.75in 0.85in;
    background-color: #0D1117;
    @bottom-center {
        content: counter(page) " / " counter(pages);
        font-size: 8pt;
        color: #666;
    }
}

body {
    font-family: 'Helvetica Neue', Arial, sans-serif;
    font-size: 10.5pt;
    line-height: 1.55;
    color: #C9D1D9;
    background-color: #0D1117;
}

h1 {
    color: #58A6FF;
    border-bottom: 2px solid #1F6FEB;
    padding-bottom: 8px;
    font-size: 20pt;
}

h2 {
    color: #58A6FF;
    border-bottom: 1px solid #21262D;
    font-size: 14pt;
    margin-top: 28px;
}

h3 { color: #79C0FF; font-size: 11.5pt; }

table { border-collapse: collapse; width: 100%; font-size: 9.5pt; }
thead th { background-color: #161B22; color: #C9D1D9; padding: 8px 10px; }
tbody td { padding: 6px 10px; border-bottom: 1px solid #21262D; }
tbody tr:nth-child(even) { background-color: #0D1117; }

pre { background-color: #161B22; border: 1px solid #30363D; padding: 12px; border-radius: 6px; }
code { background-color: #1C2128; padding: 1px 4px; border-radius: 3px; }

blockquote { border-left: 3px solid #1F6FEB; background-color: #161B22; padding: 8px 16px; }
img { max-width: 100%; margin: 14px auto; display: block; }
"""


def resolve_image_paths(md_content: str, md_dir: Path) -> str:
    """Convert relative image paths to absolute for weasyprint."""
    def replace_path(match):
        alt = match.group(1)
        path = match.group(2)
        if not path.startswith(("http://", "https://", "/")):
            abs_path = (md_dir / path).resolve()
            if abs_path.exists():
                return f"![{alt}](file://{abs_path})"
        return match.group(0)

    return re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', replace_path, md_content)


def md_to_html(md_content: str) -> str:
    """Convert markdown to HTML with extensions."""
    extensions = [
        "tables",
        "fenced_code",
        "codehilite",
        "toc",
        "smarty",
    ]
    return markdown.markdown(md_content, extensions=extensions)


def generate_pdf_weasyprint(html_content: str, css: str, output_path: str):
    """Generate PDF using weasyprint."""
    full_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>{css}</style>
</head>
<body>
{html_content}
</body>
</html>"""

    HTML(string=full_html).write_pdf(output_path)
    print(f"PDF generated: {output_path}")


def generate_pdf_pandoc(md_path: str, output_path: str):
    """Fallback PDF generation using pandoc + LaTeX."""
    import subprocess
    try:
        result = subprocess.run(
            [
                "pandoc", md_path,
                "-o", output_path,
                "--pdf-engine=xelatex",
                "-V", "geometry:margin=0.75in",
                "-V", "fontsize=11pt",
                "-V", "mainfont=Arial",
                "--highlight-style=tango",
            ],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            print(f"PDF generated (pandoc): {output_path}")
        else:
            print(f"Pandoc error: {result.stderr}")
            # Last resort: plain text
            generate_pdf_plain(md_path, output_path)
    except FileNotFoundError:
        print("WARNING: pandoc not found. Trying plain conversion.")
        generate_pdf_plain(md_path, output_path)


def generate_pdf_plain(md_path: str, output_path: str):
    """Last resort: convert MD → HTML → simple PDF using basic tools."""
    md_content = Path(md_path).read_text()
    html_content = md_to_html(md_content)

    # Try using wkhtmltopdf or similar if available
    import subprocess
    html_path = output_path.replace(".pdf", ".html")
    Path(html_path).write_text(f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>{CSS_LIGHT}</style></head>
<body>{html_content}</body></html>""")

    try:
        subprocess.run(
            ["wkhtmltopdf", "--quiet", html_path, output_path],
            capture_output=True, timeout=30,
        )
        print(f"PDF generated (wkhtmltopdf): {output_path}")
    except FileNotFoundError:
        print(f"FALLBACK: HTML saved to {html_path} — convert manually to PDF.")
        print("Install weasyprint: pip install weasyprint --break-system-packages")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Markdown to PDF Report Generator")
    parser.add_argument("--input", required=True, help="Input Markdown file")
    parser.add_argument("--output", required=True, help="Output PDF path")
    parser.add_argument("--theme", default="light", choices=["light", "dark"],
                        help="PDF theme")

    args = parser.parse_args()

    md_path = Path(args.input)
    if not md_path.exists():
        print(f"ERROR: Input file not found: {md_path}")
        sys.exit(1)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)

    md_content = md_path.read_text()
    md_content = resolve_image_paths(md_content, md_path.parent)

    css = CSS_LIGHT if args.theme == "light" else CSS_DARK

    if HTML is not None:
        html_content = md_to_html(md_content)
        generate_pdf_weasyprint(html_content, css, args.output)
    else:
        generate_pdf_pandoc(str(md_path), args.output)


if __name__ == "__main__":
    main()
