import io
import logging
from typing import Dict, List, Optional
import requests
import urllib.parse
from collections import OrderedDict
from PIL import Image

from odoo import api, models, tools, _
from odoo.exceptions import UserError
from odoo.http import request, root
from odoo.service import security
from odoo.tools.pdf import PdfFileReader, PdfFileWriter

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

    def _get_layout(self):
        return self.env.ref("plutoprint.minimal_layout_pluto", raise_if_not_found=False) or super()._get_layout()

    def _pre_render_qweb_pdf(self, report_ref, res_ids=None, data=None):
        if not data:
            data = {}
        if isinstance(res_ids, int):
            res_ids = [res_ids]
        data.setdefault("report_type", "pdf")

        if (tools.config['test_enable'] or tools.config['test_file']) and not self.env.context.get('force_report_rendering'):
            return self._render_qweb_html(report_ref, res_ids, data=data)

        self = self.with_context(webp_as_jpg=True)
        return self._render_qweb_pdf_prepare_streams(report_ref, data, res_ids=res_ids), 'pdf'

    def _render_qweb_pdf_prepare_streams(self, report_ref, data, res_ids=None):
        if not HAS_PLUTOPRINT:
            raise UserError(
                _("PlutoPrint is not available in this environment. Please install and restart workers."))

        if not data:
            data = {}
        data.setdefault('report_type', 'pdf')

        report_sudo = self._get_report(report_ref)
        has_duplicated_ids = bool(
            res_ids and len(res_ids) != len(set(res_ids)))

        collected_streams = OrderedDict()
        if res_ids:
            records = self.env[report_sudo.model].browse(res_ids)
            for record in records:
                rid = record.id
                if rid in collected_streams:
                    continue
                stream = None
                attachment = None
                if (not has_duplicated_ids and report_sudo.attachment
                        and not self._context.get("report_pdf_no_attachment")):
                    attachment = report_sudo.retrieve_attachment(record)
                    if attachment and report_sudo.attachment_use:
                        stream = io.BytesIO(attachment.raw or b"")
                        if attachment.mimetype and attachment.mimetype.startswith("image"):
                            img = Image.open(stream)
                            new_stream = io.BytesIO()
                            img.convert("RGB").save(new_stream, format="PDF")
                            stream.close()
                            stream = new_stream
                collected_streams[rid] = {
                    "stream": stream, "attachment": attachment}

        res_ids_wo_stream = [rid for rid, data_ in collected_streams.items() if not data_[
            "stream"]]
        all_res_ids_wo_stream = res_ids if has_duplicated_ids else res_ids_wo_stream
        need_engine = (not res_ids) or res_ids_wo_stream

        if not need_engine:
            return collected_streams

        add_ctx = {"debug": False}
        data.setdefault("debug", False)
        full_html = self.with_context(
            **add_ctx)._render_qweb_html(report_ref, all_res_ids_wo_stream, data=data)[0]

        unused_body, html_ids, unused_header, unused_footer, specific = self.with_context(**add_ctx)._prepare_html(
            full_html, report_model=report_sudo.model
        )
        if _logger.isEnabledFor(logging.DEBUG):
            _logger.debug("PlutoPrint render HTML bytes: %s", len(full_html))

        if (not has_duplicated_ids and report_sudo.attachment
                and set(res_ids_wo_stream) != set([x for x in html_ids if x])):
            raise UserError(_(
                "Report template “%s” has an issue.\n\n"
                "Cannot separate files to save as attachments because the template is missing "
                "data-oe-model / data-oe-id on <div class='article'>.",
                report_sudo.name,
            ))

        paperformat = self._resolve_paperformat(report_ref)
        engine_css = build_engine_css(
            paperformat, specific, landscape=self._context.get("landscape")
        )

        cookie_header = self._build_cookie_header_for_assets()

        per_body_streams: List[io.BytesIO] = []

        if has_duplicated_ids or not res_ids:
            doc = inject_css(full_html, [engine_css])
            per_body_streams.append(io.BytesIO(
                self._render_with_plutoprint(doc, cookie_header, paperformat=paperformat)))
        else:
            for rid in res_ids_wo_stream:
                doc = inject_css(full_html, [engine_css])
                pdf_bytes = self._render_with_plutoprint(
                    doc, cookie_header, paperformat=paperformat)
                per_body_streams.append(io.BytesIO(pdf_bytes))

        if has_duplicated_ids or not res_ids:
            merged = self._merge_streams(per_body_streams)
            return {False: {"stream": merged, "attachment": None}}

        if len(per_body_streams) == len(res_ids_wo_stream):
            for i, rid in enumerate(res_ids_wo_stream):
                collected_streams[rid]["stream"] = per_body_streams[i]
            return collected_streams

        html_ids_wo_none = [x for x in html_ids if x]
        if len(html_ids_wo_none) == len(per_body_streams) and set(html_ids_wo_none) == set(res_ids_wo_stream):
            rid_to_index = {rid: idx for idx,
                            rid in enumerate(html_ids_wo_none)}
            for rid in res_ids_wo_stream:
                collected_streams[rid]["stream"] = per_body_streams[rid_to_index[rid]]
            return collected_streams

        merged = self._merge_streams(per_body_streams)
        return {False: {"stream": merged, "attachment": None}}

    def _resolve_paperformat(self, report_ref):
        report = self._get_report(report_ref) if report_ref else self
        return report.get_paperformat()

    def _merge_streams(self, streams: List[io.BytesIO]) -> io.BytesIO:
        writer = PdfFileWriter()
        for s in streams:
            s.seek(0)
            reader = PdfFileReader(s)
            for i in range(reader.numPages):
                writer.addPage(reader.getPage(i))
        merged = io.BytesIO()
        writer.write(merged)
        merged.seek(0)
        for s in streams:
            try:
                s.close()
            except Exception:
                pass
        return merged

    def _build_cookie_header_for_assets(self) -> Optional[str]:
        try:
            if request and request.db:
                temp_session = root.session_store.new()
                temp_session.update(
                    {**request.session, 'debug': '', '_trace_disable': True})
                if temp_session.uid:
                    temp_session.session_token = security.compute_session_token(
                        temp_session, self.env)
                root.session_store.save(temp_session)
                return f"session_id={temp_session.sid}"
        except Exception:
            _logger.exception(
                "Failed to create temporary session cookie for report assets.")
        return None

    def _render_with_plutoprint(self, html_bytes: bytes, cookie_header: Optional[str], paperformat=None) -> bytes:
        if not HAS_PLUTOPRINT:
            raise UserError(_("PlutoPrint is not available."))

        import plutoprint

        base_url = self.env["ir.config_parameter"].sudo().get_param(
            "web.base.url") or "http://localhost"

        class OdooResourceFetcher(plutoprint.ResourceFetcher):
            def __init__(self, base_url: str, cookie_header: Optional[str], timeout: int = 6):
                self.base_url = base_url.rstrip("/")
                self.cookie_header = cookie_header
                self.timeout = timeout
                self._cache: Dict[str, "plutoprint.ResourceData"] = {}

            def fetch_url(self, url: str) -> "plutoprint.ResourceData":
                if not (url.startswith("http://") or url.startswith("https://") or url.startswith("data:")):
                    url = urllib.parse.urljoin(
                        self.base_url + "/", url.lstrip("/"))

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
                    resp = requests.get(
                        url, headers=headers, timeout=self.timeout, allow_redirects=True)
                    if resp.status_code == 404:
                        rd = plutoprint.ResourceData(
                            b"", "application/octet-stream", "")
                    else:
                        resp.raise_for_status()
                        ctype = resp.headers.get(
                            "Content-Type", "application/octet-stream").split(";")[0].strip()
                        enc = resp.encoding or "utf-8" if ctype.startswith(
                            "text/") or ctype in ("application/xml", "image/svg+xml") else ""
                        rd = plutoprint.ResourceData(resp.content, ctype, enc)
                except Exception:
                    rd = plutoprint.ResourceData(
                        b"", "application/octet-stream", "")

                self._cache[url] = rd
                return rd

        page_size = plutoprint.PAGE_SIZE_A4
        if paperformat:
            format_key = (paperformat.format or "").upper()
            _logger.info(
                "PlutoPrint paperformat received: name=%s format=%s orientation=%s page_width=%s page_height=%s margins(top/right/bottom/left)=%s/%s/%s/%s",
                getattr(paperformat, "name", None),
                getattr(paperformat, "format", None),
                getattr(paperformat, "orientation", None),
                getattr(paperformat, "page_width", None),
                getattr(paperformat, "page_height", None),
                getattr(paperformat, "margin_top", None),
                getattr(paperformat, "margin_right", None),
                getattr(paperformat, "margin_bottom", None),
                getattr(paperformat, "margin_left", None),
            )
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

            if paperformat.orientation == "Landscape":
                page_size = page_size.landscape()
            else:
                page_size = page_size.portrait()

            margins = plutoprint.PageMargins(
                top=paperformat.margin_top * plutoprint.UNITS_MM,
                right=paperformat.margin_right * plutoprint.UNITS_MM,
                bottom=paperformat.margin_bottom * plutoprint.UNITS_MM,
                left=paperformat.margin_left * plutoprint.UNITS_MM,
            )
        else:
            margins = plutoprint.PAGE_MARGINS_NONE

        book = plutoprint.Book(
            page_size,
            margins,
            media=plutoprint.MEDIA_TYPE_PRINT
        )
        book.custom_resource_fetcher = OdooResourceFetcher(
            base_url, cookie_header)

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

    @api.model
    def get_wkhtmltopdf_state(self):
        return "ok"
