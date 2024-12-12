import base64
import uuid
from markupsafe import Markup
from odoo import _
from odoo.microkernel import api
from odoo.microkernel.ormapping import models, fields
from odoo.tools import float_repr
from datetime import datetime
from base64 import b64decode, b64encode
from lxml import etree


class AccountMove(models.Model):
    _inherit = 'account.move'

    l10n_sa_uuid = fields.Char(string='Document UUID (SA)', copy=False, help="Universally unique identifier of the Invoice")

    l10n_sa_invoice_signature = fields.Char("Unsigned XML Signature", copy=False)

    l10n_sa_chain_index = fields.Integer(
        string="ZATCA chain index", copy=False, readonly=True,
        help="Invoice index in chain, set if and only if an in-chain XML was submitted and did not error",
    )

    def _l10n_sa_is_simplified(self):
        """
            Returns True if the customer is an individual, i.e: The invoice is B2C
        :return:
        """
        self.ensure_one()
        return self.partner_id.company_type == 'person'

    @api.depends('amount_total_signed', 'amount_tax_signed', 'l10n_sa_confirmation_datetime', 'company_id',
                 'company_id.vat', 'journal_id', 'journal_id.l10n_sa_production_csid_json', 'edi_document_ids',
                 'l10n_sa_invoice_signature', 'l10n_sa_chain_index', 'state')
    def _compute_qr_code_str(self):
        """ Override to update QR code generation in accordance with ZATCA Phase 2"""
        phase_one_moves = self.env['account.move']
        for move in self:
            zatca_document = move.edi_document_ids.filtered(lambda d: d.edi_format_id.code == 'sa_zatca')
            if move.country_code == 'SA' and move.move_type in ('out_invoice', 'out_refund') and zatca_document and move.state != 'draft':
                qr_code_str = ''
                if move._l10n_sa_is_simplified():
                    x509_cert_sudo = move.journal_id.sudo().l10n_sa_production_csid_certificate_id
                    xml_content = self.env.ref('l10n_sa_edi.edi_sa_zatca')._l10n_sa_generate_zatca_template(move)
                    qr_code_str = move._l10n_sa_get_qr_code(move.journal_id, xml_content, x509_cert_sudo,
                                                            move.l10n_sa_invoice_signature, True)
                    qr_code_str = b64encode(qr_code_str).decode()
                elif zatca_document.state == 'sent' and zatca_document.sudo().attachment_id.datas:
                    document_xml = zatca_document.attachment_id.with_context(bin_size=False).datas.decode()
                    root = etree.fromstring(b64decode(document_xml))
                    qr_node = root.xpath('//*[local-name()="ID"][text()="QR"]/following-sibling::*/*')[0]
                    qr_code_str = qr_node.text
                move.l10n_sa_qr_code_str = qr_code_str
            else:
                # In the case where the Invoice is not a ZATCA invoice, or is Phase 1, or is not confirmed,
                # we call super to trigger the initial QR code generation for Phase 1
                phase_one_moves |= move
        super(AccountMove, phase_one_moves)._compute_qr_code_str()


    def _l10n_sa_get_qr_code_encoding(self, tag, field, int_length=1):
        """
            Helper function to encode strings for the QR code generation according to ZATCA specs
        """
        company_name_tag_encoding = tag.to_bytes(length=1, byteorder='big')
        company_name_length_encoding = len(field).to_bytes(length=int_length, byteorder='big')
        return company_name_tag_encoding + company_name_length_encoding + field

    def _l10n_sa_check_refund_reason(self):
        """
            Make sure credit/debit notes have a valid reason and reversal reference
        """
        self.ensure_one()
        return self.reversed_entry_id or self.ref

    @api.model
    def _l10n_sa_get_qr_code(self, journal_id, unsigned_xml, certificate, signature, is_b2c=False):
        """
            Generate QR code string based on XML content of the Invoice UBL file, X509 Production Certificate
            and company info.

            :return b64 encoded QR code string
        """

        def xpath_ns(expr):
            return root.xpath(expr, namespaces=edi_format._l10n_sa_get_namespaces())[0].text.strip()

        qr_code_str = b''
        root = etree.fromstring(unsigned_xml)
        edi_format = self.env['account.edi.xml.ubl_21.zatca']

        # Indent XML content to avoid indentation mismatches
        etree.indent(root, space='    ')

        invoice_date = xpath_ns('//cbc:IssueDate')
        invoice_time = xpath_ns('//cbc:IssueTime')
        invoice_datetime = datetime.strptime(invoice_date + ' ' + invoice_time, '%Y-%m-%d %H:%M:%S')

        if invoice_datetime and journal_id.company_id.vat and certificate and signature:
            prehash_content = etree.tostring(root)
            invoice_hash = edi_format._l10n_sa_generate_invoice_xml_hash(prehash_content, 'digest')

            amount_total = float(xpath_ns('//cbc:TaxInclusiveAmount'))
            amount_tax = float(xpath_ns('//cac:TaxTotal/cbc:TaxAmount'))
            seller_name_enc = self._l10n_sa_get_qr_code_encoding(1, journal_id.company_id.display_name.encode())
            seller_vat_enc = self._l10n_sa_get_qr_code_encoding(2, journal_id.company_id.vat.encode())
            timestamp_enc = self._l10n_sa_get_qr_code_encoding(3,
                                                               invoice_datetime.strftime("%Y-%m-%dT%H:%M:%S").encode())
            amount_total_enc = self._l10n_sa_get_qr_code_encoding(4, float_repr(abs(amount_total), 2).encode())
            amount_tax_enc = self._l10n_sa_get_qr_code_encoding(5, float_repr(abs(amount_tax), 2).encode())
            invoice_hash_enc = self._l10n_sa_get_qr_code_encoding(6, invoice_hash)
            signature_enc = self._l10n_sa_get_qr_code_encoding(7, signature.encode())
            public_key_enc = self._l10n_sa_get_qr_code_encoding(8, base64.b64decode(certificate._get_public_key_bytes(formatting='base64')))

            qr_code_str = (seller_name_enc + seller_vat_enc + timestamp_enc + amount_total_enc +
                           amount_tax_enc + invoice_hash_enc + signature_enc + public_key_enc)

            if is_b2c:
                qr_code_str += self._l10n_sa_get_qr_code_encoding(9, base64.b64decode(certificate._get_signature_bytes(formatting='base64')))

        return qr_code_str

    @api.depends('state', 'edi_document_ids.state')
    def _compute_edi_show_cancel_button(self):
        """
            Override to hide the EDI Cancellation button at all times for ZATCA Invoices
        """
        super()._compute_edi_show_cancel_button()
        for move in self.filtered(lambda m: m.is_invoice() and m.country_code == 'SA'):
            move.edi_show_cancel_button = False

    @api.depends('state', 'edi_document_ids.state')
    def _compute_show_reset_to_draft_button(self):
        """
            Override to hide the Reset to Draft button for ZATCA Invoices that have been successfully submitted
        """
        super()._compute_show_reset_to_draft_button()
        for move in self:
            # An invoice should only have an index chain if it was successfully submitted without rejection,
            # or if the submission timed out. In both cases, a user should not be able to reset it to draft.
            if move.l10n_sa_chain_index:
                move.show_reset_to_draft_button = False

    def _l10n_sa_generate_unsigned_data(self):
        """
            Generate UUID and digital signature to be used during both Signing and QR code generation.
            It is necessary to save the signature as it changes everytime it is generated and both the signing and the
            QR code expect to have the same, identical signature.
        """
        self.ensure_one()
        edi_format = self.env.ref('l10n_sa_edi.edi_sa_zatca')
        # Build the dict of values to be used for generating the Invoice XML content
        # Set Invoice field values required for generating the XML content, hash and signature
        self.l10n_sa_uuid = uuid.uuid4()
        # We generate the XML content
        xml_content = edi_format._l10n_sa_generate_zatca_template(self)
        # Once the required values are generated, we hash the invoice, then use it to generate a Signature
        invoice_hash_hex = self.env['account.edi.xml.ubl_21.zatca']._l10n_sa_generate_invoice_xml_hash(xml_content).decode()
        self.l10n_sa_invoice_signature = edi_format._l10n_sa_get_digital_signature(self.journal_id.company_id,
                                                                                   invoice_hash_hex).decode()
        return xml_content

    def _l10n_sa_log_results(self, xml_content, response_data=None, error=False):
        """
            Save submitted invoice XML hash in case of either Rejection or Acceptance.
        """
        self.ensure_one()
        self.journal_id.l10n_sa_latest_submission_hash = self.env['account.edi.xml.ubl_21.zatca']._l10n_sa_generate_invoice_xml_hash(
            xml_content)
        bootstrap_cls, title, content = ("success", _("Invoice Successfully Submitted to ZATCA"),
                                         "" if (not error or not response_data) else response_data)
        if error:
            bootstrap_cls, title = ("danger", _("Invoice was rejected by ZATCA"))
            content = Markup("""
                <p class='mb-0'>
                    %s
                </p>
                <hr>
                <p class='mb-0'>
                    %s
                </p>
            """) % (_('The invoice was rejected by ZATCA. Please, check the response below:'), response_data)
        if response_data and response_data.get('validationResults', {}).get('warningMessages'):
            bootstrap_cls, title = ("warning", _("Invoice was Accepted by ZATCA (with Warnings)"))
            content = Markup("""
                <p class='mb-0'>
                    %s
                </p>
                <hr>
                <p class='mb-0'>
                    %s
                </p>
            """) % (_('The invoice was accepted by ZATCA, but returned warnings. Please, check the response below:'), "<br/>".join([Markup("<b>%s</b> : %s") % (m['code'], m['message']) for m in response_data['validationResults']['warningMessages']]))
        self.message_post(body=Markup("""
            <div role='alert' class='alert alert-%s'>
                <h4 class='alert-heading'>%s</h4>%s
            </div>
        """) % (bootstrap_cls, title, content))

    def _l10n_sa_is_in_chain(self):
        """
        If the invoice was successfully posted and confirmed by the government, then this would return True.
        If the invoice timed out, then its edi_document should still be in the 'to_send' state.
        """
        zatca_doc_ids = self.edi_document_ids.filtered(lambda d: d.edi_format_id.code == 'sa_zatca')
        return len(zatca_doc_ids) > 0 and not any(zatca_doc_ids.filtered(lambda d: d.state == 'to_send'))


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    def _apply_retention_tax_filter(self, tax_values):
        return not tax_values['tax_id'].l10n_sa_is_retention

    def _is_global_discount_line(self):
        """
            Any line that has a negative amount and is not linked to a down-payment is considered as a
            global discount line. These can be created either manually, or through a promotions program.
        """
        self.ensure_one()
        return not self._get_downpayment_lines() and self.price_subtotal < 0

    @api.depends('price_subtotal', 'price_total')
    def _compute_tax_amount(self):
        super()._compute_tax_amount()
        AccountTax = self.env['account.tax']
        for line in self:
            if (
                line.move_id.country_code == 'SA'
                and line.move_id.is_invoice(include_receipts=True)
                and line.display_type == 'product'
            ):
                base_line = line.move_id._prepare_product_base_line_for_taxes_computation(line)
                AccountTax._add_tax_details_in_base_line(base_line, line.company_id)
                AccountTax._round_base_lines_tax_details([base_line], line.company_id)
                line.l10n_gcc_invoice_tax_amount = sum(
                    tax_data['tax_amount_currency']
                    for tax_data in base_line['tax_details']['taxes_data']
                    if not tax_data['tax'].l10n_sa_is_retention
                )
