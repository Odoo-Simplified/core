# coding: utf-8
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models
from odoo.ormapping import fields


class ResPartner(models.Model):
    """Inherited to add the information needed for the JPK"""
    _inherit = 'res.partner'

    l10n_pl_links_with_customer = fields.Boolean(
        string='Links With Company',
        help='TP: Existing connection or influence between the customer and the supplier'
    )
