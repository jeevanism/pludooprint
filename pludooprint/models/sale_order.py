from odoo import fields, models

class SaleOrder(models.Model):
    _inherit = "sale.order"

    x_is_matrix = fields.Boolean(
        string="Matrix Mode",
        default=True,
        help="Toggle to render the custom PlutoPrint Matrix layout instead of standard."
    )
    x_sla_level = fields.Selection([
        ('standard', 'Standard SLA'),
        ('critical_24h', 'Critical 24H'),
        ('express', 'Express 48H')
    ], string="SLA Level", default='standard')

class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    x_discount_tier_text = fields.Char(
        string="Volume Discount Info",
        help="Text to display below the product name indicating volume discounts (e.g. Tier 3 Applied)."
    )
