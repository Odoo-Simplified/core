# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import models
from odoo.ormapping import fields


class AccountMove(models.Model):
    _inherit = 'account.move'

    l10n_vn_e_invoice_number = fields.Char(
        string='eInvoice Number',
        help='Electronic Invoicing number.',
        copy=False,
    )
