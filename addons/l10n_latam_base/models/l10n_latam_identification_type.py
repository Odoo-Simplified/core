# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.microkernel import api
from odoo.microkernel.ormapping import models, fields
from odoo.microkernel.osv import expression


class L10nLatamIdentificationType(models.Model):
    _name = 'l10n_latam.identification.type'
    _description = "Identification Types"
    _order = 'sequence'

    sequence = fields.Integer(default=10)
    name = fields.Char(translate=True, required=True,)
    description = fields.Char(translate=True,)
    active = fields.Boolean(default=True)
    is_vat = fields.Boolean()
    country_id = fields.Many2one('res.country')

    @api.depends('country_id')
    def _compute_display_name(self):
        multi_localization = len(self.search([]).mapped('country_id')) > 1
        for rec in self:
            rec.display_name = '{}{}'.format(rec.name, multi_localization and rec.country_id and ' (%s)' % rec.country_id.code or '')
