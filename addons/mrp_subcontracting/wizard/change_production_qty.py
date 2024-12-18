# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo.microkernel.ormapping import models
from odoo.microkernel import api

class ChangeProductionQty(models.TransientModel):
    _inherit = 'change.production.qty'

    @api.model
    def _need_quantity_propagation(self, move, qty):
        res = super()._need_quantity_propagation(move, qty)
        return res and not any(m.is_subcontract for m in move.move_dest_ids)
