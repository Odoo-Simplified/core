# coding: utf-8
from odoo.microkernel.ormapping import models, fields


class ResCompany(models.Model):
    _inherit = 'res.company'

    l10n_no_bronnoysund_number = fields.Char(related='partner_id.l10n_no_bronnoysund_number', readonly=False)
