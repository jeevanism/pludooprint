from typing import Dict, List, Optional

def _build_engine_css_template(size_css: str, mr: float, ml: float, mt: float, mb: float) -> str:
    return f"""
        @page {{
            {size_css}
            margin: {mt}mm {mr}mm {mb}mm {ml}mm;
            @top-center {{
                content: element(report_header);
            }}
            @bottom-center {{
                content: element(report_footer);
            }}
        }}

        html, body, body.overflow-hidden {{
            height: auto !important;
            overflow: visible !important;
        }}

        #odoo_pluto_header {{
            position: running(report_header);
            width: 100%;
            display: block !important;
            visibility: visible !important;
        }}

        #odoo_pluto_footer {{
            position: running(report_footer);
            width: 100%;
            display: block !important;
            visibility: visible !important;
        }}

        #odoo_pluto_header .header,
        #odoo_pluto_footer .footer {{
            display: block !important;
            visibility: visible !important;
            margin-left: 0 !important;
            margin-right: 0 !important;
            padding-left: 0 !important;
            padding-right: 0 !important;
        }}

        /* Format page numbering in-place */
        span.page::after {{
            content: counter(page) !important;
        }}

        span.topage::after {{
            content: counter(pages) !important;
        }}

        /* Repeat table headers and prevent row breaks */
        thead {{
            display: table-header-group !important;
        }}

        tr {{
            page-break-inside: avoid !important;
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

    mr = float(paper.margin_right)
    ml = float(paper.margin_left)
    mt = float(specific_args.get("data-report-margin-top") or paper.margin_top)
    mb = float(specific_args.get("data-report-margin-bottom") or paper.margin_bottom)

    if paper.format and paper.format != "custom" and landscape:
        size_css = f"size: {paper.format} landscape;"
    elif landscape and paper.page_width and paper.page_height:
        w = f"{paper.page_height}mm"
        h = f"{paper.page_width}mm"
        size_css = f"size: {w} {h};"

    return _build_engine_css_template(size_css=size_css, mr=mr, ml=ml, mt=mt, mb=mb)

def inject_css(doc_bytes: bytes, css_list: List[str]) -> bytes:
    marker = b"<head>"
    pos = doc_bytes.find(marker)
    if pos != -1:
        injection = ("<style>" + "\n".join(css_list) + "</style>").encode("utf-8")
        return doc_bytes[:pos + len(marker)] + injection + doc_bytes[pos + len(marker):]
    return doc_bytes
