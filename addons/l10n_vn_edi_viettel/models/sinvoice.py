# Part of Odoo. See LICENSE file for full copyright and licensing details.

from collections import defaultdict

from odoo import _
from odoo.microkernel import api
from odoo.microkernel.ormapping import models, fields
from odoo.exceptions import UserError


# Invoice template that needs to be passed to Sinvoice and will determine the format of the resulting
# invoice pdf on their system
class SInvoiceTemplate(models.Model):
    _name = 'l10n_vn_edi_viettel.sinvoice.template'
    _description = 'SInvoice template'

    name = fields.Char(
        string='Template Code',
        required=True,
    )
    template_invoice_type = fields.Selection(
        selection=[
            # Circular 32 being deprecated, only display types according to the Circular 78
            ('1', '1 - Value-added invoice'),
            ('2', '2 - Sales invoice'),
            ('3', '3 - Public assets sales'),
            ('4', '4 - National reserve sales'),
            ('5', '5 - Invoice for national reserve sales'),
            ('6', '6 - Warehouse release note'),
        ],
        required=True,
    )
    invoice_symbols_ids = fields.One2many(
        comodel_name='l10n_vn_edi_viettel.sinvoice.symbol',
        inverse_name='invoice_template_id',
    )

    _sql_constraints = [
        ('name_uniq', 'unique (name)', 'The template code must be unique!')
    ]

    @api.constrains('name', 'template_invoice_type')
    def _constrains_changes(self):
        """
        Multiple API endpoints will use these data, we should thus not allow changing them if they have been used
        for any invoices sent to sinvoice.
        """
        # The conditions are the same. If any symbols of the template are being used, we shouldn't allow editing it.
        self.invoice_symbols_ids._constrains_changes()


# Invoice symbol that needs to be passed to Sinvoice and will determine the prefix of the
# invoice number on their system
class SInvoiceSymbol(models.Model):
    _name = 'l10n_vn_edi_viettel.sinvoice.symbol'
    _description = 'SInvoice symbol'
    """
    The invoice symbols are made of multiple parts.
    The symbols characters have meanings that will influence the resulting invoices:

    The first character is either C (invoice with code from tax department) or K (without)
    It is then followed by two number which represent the current year (24 in 2024)
    Next, a single character representing additional invoice information:

        T: E-invoices registered with tax authorities by enterprises, organizations or household businesses;
        D: E-invoices used for sale of public property or national reserve goods or special e-invoices that do not have some mandatory contents of the “T” invoices;
        L: E-invoices issued separately by tax authorities;
        M: E-invoices generated by cash registers;
        N: Electronic delivery and internal consignment notes;
        B: Electronic delivery notes for goods sent to sales agents;
        G: VAT invoices in the form of electronic stamps, tickets or cards;
        H: Sales invoices in the form of electronic stamps, tickets or cards.

    Finally, it ends with two characters that shall be decided by the seller for their management requirements.
    """

    name = fields.Char(
        string='Symbol',
        required=True,
    )
    invoice_template_id = fields.Many2one(
        comodel_name='l10n_vn_edi_viettel.sinvoice.template',
        required=True,
    )

    _sql_constraints = [
        ('name_template_uniq', 'unique (name, invoice_template_id)', 'The combination symbol/template must be unique!')
    ]

    @api.constrains('name', 'invoice_template_id')
    def _constrains_changes(self):
        """
        Multiple API endpoints will use these data, we should thus not allow changing them if they have been used
        for any invoices sent to sinvoice.
        """
        invoice_counts = self.env['account.move']._read_group(
            domain=[
                ('l10n_vn_edi_invoice_symbol', 'in', self.ids),
                ('l10n_vn_edi_invoice_state', 'not in', ('ready_to_send', False)),  # Only matches sent invoices.
            ],
            groupby=['l10n_vn_edi_invoice_symbol'],
            aggregates=['__count'],
        )
        invoices_per_symbol = defaultdict(int)
        for symbol, count in invoice_counts:
            invoices_per_symbol[symbol.id] = count

        for record in self:
            if invoices_per_symbol[record.id] > 0:
                raise UserError(_('You cannot change the symbol value or template of the symbol %s because it has '
                                  'already been used to send invoices.', record.name))

    @api.depends('name', 'invoice_template_id')
    def _compute_display_name(self):
        """ As we allow multiple of the same symbol name, we need to also display the template to differentiate. """
        for symbol in self:
            symbol.display_name = f'{symbol.name} ({symbol.invoice_template_id.name})'
