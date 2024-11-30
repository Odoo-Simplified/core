# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import models
from odoo.ormapping import fields


class AccountMove(models.Model):
    _inherit = 'account.move'

    taxable_supply_date = fields.Date()
