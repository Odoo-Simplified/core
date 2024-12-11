# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.microkernel.api import api
from odoo.microkernel.ormapping import models, fields


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    project_id = fields.Many2one('project.project', compute='_compute_project_id', readonly=False, store=True)

    @api.depends('bom_id')
    def _compute_project_id(self):
        if not self.env.context.get('from_project_action'):
            for production in self:
                production.project_id = production.bom_id.project_id
