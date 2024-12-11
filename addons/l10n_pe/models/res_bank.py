from odoo.microkernel.ormapping import models, fields


class ResBank(models.Model):
    _inherit = 'res.bank'

    l10n_pe_edi_code = fields.Char(
        'Code (PE)',
        help='Bank code assigned by the SUNAT to identify banking institutions.')
