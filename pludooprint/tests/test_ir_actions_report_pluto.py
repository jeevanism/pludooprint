import io
from unittest.mock import patch, Mock
from odoo.tests import TransactionCase, tagged
from odoo.exceptions import UserError
from odoo.tools import config
try:
    from odoo.tools.pdf import PdfWriter, PdfReader

    def _make_writer():
        return PdfWriter()

    def _add_blank_page(writer, width=72, height=72):
        writer.add_blank_page(width=width, height=height)

    def _write_writer(writer, buf):
        writer.write(buf)

    def _read_reader(stream):
        return PdfReader(stream)

    def _num_pages(reader):
        return len(reader.pages)
except Exception:
    from odoo.tools.pdf import PdfFileWriter, PdfFileReader

    def _make_writer():
        return PdfFileWriter()

    def _add_blank_page(writer, width=72, height=72):
        writer.addBlankPage(width=width, height=height)

    def _write_writer(writer, buf):
        writer.write(buf)

    def _read_reader(stream):
        return PdfFileReader(stream)

    def _num_pages(reader):
        return reader.numPages
ADDON = __package__.split('.')[2]
TARGET = f"odoo.addons.{ADDON}.models.ir_actions_report_pluto"


class DummyReport:
    report_name = 'test.report_name'
    model = "res.partner"
    attachment = False
    attachment_use = False
    is_invoice_report = False

    def retrieve_attachment(self, rec):
        return None

    def get_paperformat(self):
        class DummyPaper:
            format = "A4"
            page_width = page_height = None
            margin_top = margin_bottom = margin_left = margin_right = 10
            header_spacing = 0
        return DummyPaper()


@tagged('post_install', '-at_install')
class TestIrActionsReportPlutoHelpers(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Report = cls.env['ir.actions.report']

    def _tiny_pdf(self):
        buf = io.BytesIO()
        writer = _make_writer()
        _add_blank_page(writer, width=72, height=72)
        _write_writer(writer, buf)
        buf.seek(0)
        return buf

    def test_paperformat_to_css_rules_basic_and_landscape(self):
        rpt = self.Report

        class P:
            format = "A4"
            page_width = None
            page_height = None
            margin_top = 10
            margin_bottom = 15
            margin_left = 7
            margin_right = 7
            header_spacing = 3
        css1 = rpt._paperformat_to_css_rules(
            P, specific_args={'data-report-header-spacing': 5}, landscape=False
        )
        assert "size: A4;" in css1, css1
        assert "padding-bottom: 5mm" in css1, css1
        css2 = rpt._paperformat_to_css_rules(
            P, specific_args={'data-report-landscape': True}, landscape=None
        )
        assert "size: A4 landscape;" in css2, css2

    def test_merge_streams_combines_pages(self):
        rpt = self.Report
        a = self._tiny_pdf()
        b = self._tiny_pdf()
        merged = rpt._merge_streams([a, b])
        merged.seek(0)
        reader = _read_reader(merged)
        assert _num_pages(reader) == 2, "Merged PDF should have 2 pages"


@tagged('post_install', '-at_install')
class TestIrActionsReportPlutoBehavior(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Report = cls.env['ir.actions.report']
        cls.dummy_report_ref = f"{ADDON}.dummy_report"

    def _dummy_report_obj(self):
        class DummyPaper:
            format = "A4"
            page_width = page_height = None
            margin_top = margin_bottom = margin_left = margin_right = 10
            header_spacing = 0

        class DummyReport:
            report_name = "x.report_dummy"
            model = "res.partner"
            attachment = False
            attachment_use = False
            is_invoice_report = False
            def retrieve_attachment(self, rec): return None
            def get_paperformat(self): return DummyPaper()
        return DummyReport()

    def test_pre_render_qweb_pdf_respects_test_mode(self):
        from odoo import tools
        rpt = self.Report
        old = tools.config.get('test_enable')
        tools.config['test_enable'] = True
        try:
            with patch.object(type(rpt), "_get_report", return_value=self._dummy_report_obj()), \
                patch.object(type(rpt), "_render_qweb_html",
                             return_value=(b"<html>ok</html>", "html")) as mock_html:
                html_or_streams, out_type = rpt._pre_render_qweb_pdf(
                    "pludooprint.report_dummy",
                    res_ids=[1],
                    data={}
                )
                mock_html.assert_called_once()
                assert out_type == "html"
                assert isinstance(
                    html_or_streams, (bytes, bytearray)) or html_or_streams is not None
        finally:
            tools.config['test_enable'] = old

    def test_render_prepare_streams_raises_without_plutoprint(self):
        rpt = self.Report
        with patch.object(type(rpt), "_get_report", return_value=self._dummy_report_obj()), \
                patch(f"{TARGET}.HAS_PLUTOPRINT", False):
            with self.assertRaises(UserError):
                rpt._render_qweb_pdf_prepare_streams(
                    "pludooprint.report_dummy", data={}, res_ids=[1])

    def test_render_prepare_streams_with_fake_pluto(self):
        rpt = self.Report

        def _fake_render_with_plutoprint(self, html_bytes, cookie_header):
            buf = io.BytesIO()
            writer = _make_writer()
            _add_blank_page(writer, width=72, height=72)
            _write_writer(writer, buf)
            return buf.getvalue()
        with patch.object(type(rpt), "_get_report", return_value=self._dummy_report_obj()), \
                patch(f"{TARGET}.HAS_PLUTOPRINT", True), \
                patch.object(type(rpt), "_render_with_plutoprint", _fake_render_with_plutoprint), \
                patch.object(type(rpt), "_render_qweb_html",
                             return_value=(b"<html><head></head><body>"
                                           b"<div id='wrapwrap'><div class='article' "
                                           b"data-oe-model='res.partner' data-oe-id='1'>X</div></div>"
                                           b"</body></html>", "html")), \
                patch.object(type(rpt), "_prepare_html", return_value=(
                    b"<html><head></head><body>"
                    b"<div id='wrapwrap'><div class='article' data-oe-model='res.partner' data-oe-id='1'>X</div></div>"
                    b"</body></html>",
                    [1], None, None, {}
                )), \
                patch.object(type(rpt), "_resolve_paperformat") as mock_paper:
            class DummyPaper:
                format = "A4"
                page_width = page_height = None
                margin_top = margin_bottom = margin_left = margin_right = 10
                header_spacing = 0
            mock_paper.return_value = DummyPaper()
            result = rpt._render_qweb_pdf_prepare_streams(
                "pludooprint.report_dummy", data={}, res_ids=[1])
            assert 1 in result, "Expected key for res_id=1 in mapping"
            assert result[1]["stream"] is not None, "Expected a PDF stream for res_id=1"
