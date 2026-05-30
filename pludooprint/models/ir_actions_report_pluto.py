import io
import logging
import requests
import urllib.parse
from typing import Dict, List, Optional

from odoo import api, models, tools, _
from odoo.exceptions import UserError
from odoo.http import request, root
from odoo.service import security

from .plutoprint_helpers import build_engine_css, inject_css

_logger = logging.getLogger(__name__)

try:
    import plutoprint
    HAS_PLUTOPRINT = True
except Exception as e:
    HAS_PLUTOPRINT = False
    _logger.exception("PlutoPrint import failed: %s", e)


class IrActionsReportPluto(models.Model):
    _inherit = "ir.actions.report"

    @api.model
    def get_wkhtmltopdf_state(self):
        # Override to stop Odoo's frontend from showing the missing wkhtmltopdf warning
        return "ok"

    @api.model
    def _run_wkhtmltopdf(
            self,
            bodies,
            report_ref=False,
            header=None,
            footer=None,
            landscape=False,
            specific_paperformat_args=None,
            set_viewport_size=False):
        """
        Intercept Odoo's PDF generation and route it directly to PlutoPrint.
        """
        if not HAS_PLUTOPRINT:
            raise UserError(
                _("PlutoPrint is not available in this environment. Please install and restart workers."))

        # 1. Resolve Paperformat
        paperformat = self._get_report(report_ref).get_paperformat() if report_ref else self.get_paperformat()
        engine_css = build_engine_css(
            paperformat, specific_paperformat_args, landscape=landscape
        )

        # 2. Build Cookie Header for Asset Fetching
        cookie_header = self._build_cookie_header_for_assets()

        # 3. Process and Render each Page Body
        rendered_pdfs: List[bytes] = []
        for body in bodies:
            recombined_html = self._recombine_html(body, header, footer)
            doc_bytes = inject_css(recombined_html.encode("utf-8"), [engine_css])
            
            pdf_bytes = self._render_with_plutoprint(
                doc_bytes,
                cookie_header,
                paperformat=paperformat,
                specific=specific_paperformat_args,
                landscape=landscape
            )
            rendered_pdfs.append(pdf_bytes)

        # 4. Merge all PDFs using Odoo's native PDF merger
        if len(rendered_pdfs) == 1:
            return rendered_pdfs[0]

        streams = [io.BytesIO(pdf) for pdf in rendered_pdfs]
        merged_stream = self._merge_pdfs(streams)
        pdf_bytes = merged_stream.getvalue()
        
        # Cleanup streams
        merged_stream.close()
        for s in streams:
            try:
                s.close()
            except Exception:
                pass

        return pdf_bytes

    def _extract_body_content(self, html_str: str) -> str:
        if not html_str:
            return ""
        body_start_idx = html_str.find("<body")
        if body_start_idx == -1:
            return html_str
        
        tag_end_idx = html_str.find(">", body_start_idx)
        if tag_end_idx == -1:
            return html_str
            
        body_end_idx = html_str.rfind("</body>")
        if body_end_idx == -1:
            return html_str[tag_end_idx + 1:]
            
        return html_str[tag_end_idx + 1:body_end_idx]

    def _recombine_html(self, body_str: str, header_str: Optional[str], footer_str: Optional[str]) -> str:
        """
        Recombine the split header and footer blocks back into the main HTML flow.
        """
        import re

        if header_str in (False, 0, '0', 'False', None):
            header_str = ""
        if footer_str in (False, 0, '0', 'False', None):
            footer_str = ""

        if isinstance(body_str, bytes):
            body_str = body_str.decode("utf-8")
        else:
            body_str = str(body_str) if body_str is not None else ""

        if isinstance(header_str, bytes):
            header_str = header_str.decode("utf-8")
        else:
            header_str = str(header_str) if header_str is not None else ""

        if isinstance(footer_str, bytes):
            footer_str = footer_str.decode("utf-8")
        else:
            footer_str = str(footer_str) if footer_str is not None else ""

        header_content = self._extract_body_content(header_str)
        footer_content = self._extract_body_content(footer_str)
        
        # Strip display: table-row-group inline style from thead to allow repetition
        body_str = re.sub(
            r'(<thead[^>]*?\s)style=["\']display:\s*table-row-group;?["\']',
            r'\1',
            body_str,
            flags=re.IGNORECASE
        )
        
        # Insert header and footer blocks at the beginning of the <body> container
        body_idx = body_str.find("<body")
        if body_idx != -1:
            closing_idx = body_str.find(">", body_idx)
            if closing_idx != -1:
                injection = f'\n<div id="odoo_pluto_header" class="container">{header_content}</div>\n<div id="odoo_pluto_footer" class="container">{footer_content}</div>\n'
                return body_str[:closing_idx+1] + injection + body_str[closing_idx+1:]
        
        # Fallback if no body tag exists
        return f"""<!DOCTYPE html>
<html>
  <head>
    <meta charset="utf-8"/>
  </head>
  <body>
    <div id="odoo_pluto_header" class="container">{header_content}</div>
    <div id="odoo_pluto_footer" class="container">{footer_content}</div>
    {body_str}
  </body>
</html>"""

    def _build_cookie_header_for_assets(self) -> Optional[str]:
        try:
            if request and request.db:
                temp_session = root.session_store.new()
                temp_session.update({
                    **request.session,
                    'debug': '',
                    '_trace_disable': True
                })
                if temp_session.uid:
                    temp_session.session_token = security.compute_session_token(temp_session, self.env)
                root.session_store.save(temp_session)
                return f"session_id={temp_session.sid}"
        except Exception:
            _logger.exception("Failed to create temporary session cookie for report assets.")
        return None

    def _render_with_plutoprint(
            self,
            html_bytes: bytes,
            cookie_header: Optional[str],
            paperformat=None,
            specific=None,
            landscape=False) -> bytes:

        import plutoprint

        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url") or "http://localhost:8019"

        class OdooResourceFetcher(plutoprint.ResourceFetcher):
            def __init__(self, base_url: str, cookie_header: Optional[str], timeout: int = 6):
                super().__init__()
                self.base_url = base_url.rstrip("/")
                self.cookie_header = cookie_header
                self.timeout = timeout
                self._cache = {}

            def fetch_url(self, url: str) -> "plutoprint.ResourceData":
                if not (url.startswith("http://") or url.startswith("https://") or url.startswith("data:")):
                    url = urllib.parse.urljoin(self.base_url + "/", url.lstrip("/"))

                cached = self._cache.get(url)
                if cached is not None:
                    return cached

                low = url.lower()
                if low.endswith(".eot") or "fonts.odoocdn.com" in low:
                    rd = plutoprint.ResourceData(b"", "font/woff2", "")
                    self._cache[url] = rd
                    return rd

                if url.startswith("data:"):
                    rd = super().fetch_url(url)
                    self._cache[url] = rd
                    return rd

                headers = {}
                if self.cookie_header:
                    base_host = urllib.parse.urlparse(self.base_url).netloc
                    url_host = urllib.parse.urlparse(url).netloc
                    if base_host == url_host or "/web/content/" in url:
                        headers["Cookie"] = self.cookie_header

                try:
                    resp = requests.get(url, headers=headers, timeout=self.timeout, allow_redirects=True)
                    if resp.status_code == 404:
                        rd = plutoprint.ResourceData(b"", "application/octet-stream", "")
                    else:
                        resp.raise_for_status()
                        ctype = resp.headers.get("Content-Type", "application/octet-stream").split(";")[0].strip()
                        enc = resp.encoding or "utf-8" if ctype.startswith("text/") or ctype in ("application/xml", "image/svg+xml") else ""
                        rd = plutoprint.ResourceData(resp.content, ctype, enc)
                except Exception:
                    rd = plutoprint.ResourceData(b"", "application/octet-stream", "")

                self._cache[url] = rd
                return rd

        # Resolve Page Size
        page_size = plutoprint.PAGE_SIZE_A4
        if paperformat:
            format_key = (paperformat.format or "").upper()
            page_sizes = {
                "A3": plutoprint.PAGE_SIZE_A3,
                "A4": plutoprint.PAGE_SIZE_A4,
                "A5": plutoprint.PAGE_SIZE_A5,
                "B4": plutoprint.PAGE_SIZE_B4,
                "B5": plutoprint.PAGE_SIZE_B5,
                "LETTER": plutoprint.PAGE_SIZE_LETTER,
                "LEGAL": plutoprint.PAGE_SIZE_LEGAL,
                "LEDGER": plutoprint.PAGE_SIZE_LEDGER,
            }
            if format_key == "CUSTOM" and paperformat.page_width and paperformat.page_height:
                page_size = plutoprint.PageSize(
                    paperformat.page_width * plutoprint.UNITS_MM,
                    paperformat.page_height * plutoprint.UNITS_MM,
                )
            else:
                page_size = page_sizes.get(format_key, page_size)

            is_landscape = landscape or (specific and specific.get("data-report-landscape")) or (paperformat.orientation == "Landscape")
            if is_landscape:
                page_size = page_size.landscape()
            else:
                page_size = page_size.portrait()

            mt = float(specific.get("data-report-margin-top") or paperformat.margin_top) if specific else paperformat.margin_top
            mb = float(specific.get("data-report-margin-bottom") or paperformat.margin_bottom) if specific else paperformat.margin_bottom

            margins = plutoprint.PageMargins(
                top=mt * plutoprint.UNITS_MM,
                right=paperformat.margin_right * plutoprint.UNITS_MM,
                bottom=mb * plutoprint.UNITS_MM,
                left=paperformat.margin_left * plutoprint.UNITS_MM,
            )
        else:
            margins = plutoprint.PAGE_MARGINS_NONE

        book = plutoprint.Book(page_size, margins, media=plutoprint.MEDIA_TYPE_PRINT)
        book.custom_resource_fetcher = OdooResourceFetcher(base_url, cookie_header)

        book.load_data(
            html_bytes,
            mime_type="text/html",
            text_encoding="utf-8",
            base_url=base_url,
        )

        output = io.BytesIO()
        book.write_to_pdf_stream(output)
        pdf = output.getvalue()
        output.close()
        return pdf
