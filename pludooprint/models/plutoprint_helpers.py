from typing import Dict, List, Optional


def _build_engine_css_template(size_css: str, mr: int, ml: int, mt: int = 2, mb: int = 2) -> str:
    return f"""
        @page {{
            {size_css}
            margin: {mt}mm {mr}mm {mb}mm {ml}mm;
        }}

        .header ul {{ margin-bottom: 0 !important; }}

        .header .row {{ margin-bottom: 0 !important; }}

        .header .d-flex {{
            justify-content: flex-start !important;
        }}
        .header img {{
            margin-left: 0 !important;
            margin-right: auto !important;
            align-self: flex-start !important;
        }}

        .page .topage{{
            display:none !important;
        }}

        .page::after {{
            display:none;
        }}

        .topage::after {{
            display:none;
        }}
        """


def build_engine_css(paper, specific_args: Optional[Dict], landscape: Optional[bool]) -> str:
    specific_args = specific_args or {}

    if landscape is None and specific_args.get("data-report-landscape"):
        landscape = specific_args.get("data-report-landscape") in (True, "True", "true", "1")

    size_css = ""
    if paper.format and paper.format != "custom":
        size_css = f"size: {paper.format};"
    elif paper.page_width and paper.page_height:
        w = f"{paper.page_width}mm"
        h = f"{paper.page_height}mm"
        size_css = f"size: {w} {h};"

    mr = paper.margin_right
    ml = paper.margin_left

    if paper.format and paper.format != "custom" and landscape:
        size_css = f"size: {paper.format} landscape;"
    elif landscape and paper.page_width and paper.page_height:
        w = f"{paper.page_height}mm"
        h = f"{paper.page_width}mm"
        size_css = f"size: {w} {h};"

    return _build_engine_css_template(size_css=size_css, mr=mr, ml=ml)


def inject_css(doc_bytes: bytes, css_list: List[str]) -> bytes:
    marker = b"<head>"
    pos = doc_bytes.find(marker)
    if pos != -1:
        injection = ("<style>" + "\n".join(css_list) + "</style>").encode("utf-8")
        return doc_bytes[:pos + len(marker)] + injection + doc_bytes[pos + len(marker):]
    return doc_bytes
