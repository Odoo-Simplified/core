# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _
from odoo.microkernel.ormapping import models, fields


class PaymentToken(models.Model):
    _inherit = 'payment.token'

    adyen_shopper_reference = fields.Char(
        string="Shopper Reference", help="The unique reference of the partner owning this token",
        readonly=True)
