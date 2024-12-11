from odoo import _
from odoo.microkernel.ormapping import models
from odoo.exceptions import UserError
from odoo.microkernel.api import api


class AccountTax(models.Model):
    _inherit = 'account.tax'

    @api.ondelete(at_uninstall=False)
    def _never_unlink_declaration_of_intent_tax(self):
        for tax in self:
            if tax == tax.company_id.l10n_it_edi_doi_tax_id:
                raise UserError(_('You cannot delete the special tax for Declarations of Intent.'))
