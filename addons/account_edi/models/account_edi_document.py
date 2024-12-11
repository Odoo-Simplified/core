# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
import base64
import logging

import psycopg2.errors

from odoo import _
from odoo.microkernel.api import api
from odoo.microkernel.ormapping import models, fields
from odoo.exceptions import UserError


_logger = logging.getLogger(__name__)

DEFAULT_BLOCKING_LEVEL = 'error'


class AccountEdiDocument(models.Model):
    _name = 'account.edi.document'
    _description = 'Electronic Document for an account.move'

    # == Stored fields ==
    move_id = fields.Many2one('account.move', required=True, ondelete='cascade', index=True)
    edi_format_id = fields.Many2one('account.edi.format', required=True)
    attachment_id = fields.Many2one(
        comodel_name='ir.attachment',
        groups='base.group_system',
        help="The file generated by edi_format_id when the invoice is posted (and this document is processed).",
    )
    state = fields.Selection([('to_send', 'To Send'), ('sent', 'Sent'), ('to_cancel', 'To Cancel'), ('cancelled', 'Cancelled')])
    error = fields.Html(help='The text of the last error that happened during Electronic Invoice operation.')
    blocking_level = fields.Selection(
        selection=[('info', 'Info'), ('warning', 'Warning'), ('error', 'Error')],
        help="Blocks the current operation of the document depending on the error severity:\n"
        "  * Info: the document is not blocked and everything is working as it should.\n"
        "  * Warning: there is an error that doesn't prevent the current Electronic Invoicing operation to succeed.\n"
        "  * Error: there is an error that blocks the current Electronic Invoicing operation.")

    # == Not stored fields ==
    name = fields.Char(related='attachment_id.name')
    edi_format_name = fields.Char(string='Format Name', related='edi_format_id.name')
    edi_content = fields.Binary(compute='_compute_edi_content', compute_sudo=True)

    _sql_constraints = [
        (
            'unique_edi_document_by_move_by_format',
            'UNIQUE(edi_format_id, move_id)',
            'Only one edi document by move by format',
        ),
    ]

    @api.depends('move_id', 'error', 'state')
    def _compute_edi_content(self):
        for doc in self:
            res = b''
            if doc.state in ('to_send', 'to_cancel'):
                move = doc.move_id
                config_errors = doc.edi_format_id._check_move_configuration(move)
                if config_errors:
                    res = base64.b64encode('\n'.join(config_errors).encode('UTF-8'))
                else:
                    move_applicability = doc.edi_format_id._get_move_applicability(move)
                    if move_applicability and move_applicability.get('edi_content'):
                        res = base64.b64encode(move_applicability['edi_content'](move))
            doc.edi_content = res

    def action_export_xml(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url':  '/web/content/account.edi.document/%s/edi_content' % self.id
        }

    def _prepare_jobs(self):
        """Creates a list of jobs to be performed by '_process_job' for the documents in self.
        Each document represent a job, BUT if multiple documents have the same state, edi_format_id,
        doc_type invoice and company_id AND the edi_format_id supports batching, they are grouped
        into a single job.

        :returns:  [{
            'documents': account.edi.document,
            'method_to_call': str,
        }]
        """
        # Classify jobs by (edi_format, edi_doc.state, doc_type, move.company_id, custom_key)
        to_process = {}
        for state, edi_flow in (('to_send', 'post'), ('to_cancel', 'cancel')):
            documents = self.filtered(lambda d: d.state == state and d.blocking_level != 'error')
            for edi_doc in documents:
                edi_format = edi_doc.edi_format_id
                move = edi_doc.move_id
                move_applicability = edi_doc.edi_format_id._get_move_applicability(move) or {}

                batching_key = [edi_format, state, move.company_id]
                custom_batching_key = f'{edi_flow}_batching'
                if move_applicability.get(custom_batching_key):
                    batching_key += list(move_applicability[custom_batching_key](move))
                else:
                    batching_key.append(move.id)

                batch = to_process.setdefault(tuple(batching_key), {
                    'documents': self.env['account.edi.document'],
                    'method_to_call': move_applicability.get(edi_flow),
                })
                batch['documents'] |= edi_doc

        return list(to_process.values())

    @api.model
    def _process_job(self, job):
        """Post or cancel move_id by calling the related methods on edi_format_id.

        :param job:  {
            'documents': account.edi.document,
            'method_to_call': str,
        }
        """
        def _postprocess_post_edi_results(documents, edi_result):
            attachments_to_unlink = self.env['ir.attachment']
            for document in documents:
                move = document.move_id
                move_result = edi_result.get(move, {})
                if move_result.get('attachment'):
                    old_attachment = document.sudo().attachment_id
                    document.sudo().attachment_id = move_result['attachment']
                    if not old_attachment.res_model or not old_attachment.res_id:
                        attachments_to_unlink |= old_attachment
                if move_result.get('success') is True:
                    document.write({
                        'state': 'sent',
                        'error': False,
                        'blocking_level': False,
                    })
                else:
                    document.write({
                        'error': move_result.get('error', False),
                        'blocking_level': move_result.get('blocking_level', DEFAULT_BLOCKING_LEVEL) if 'error' in move_result else False,
                    })

            # Attachments that are not explicitly linked to a business model could be removed because they are not
            # supposed to have any traceability from the user.
            attachments_to_unlink.sudo().unlink()

        def _postprocess_cancel_edi_results(documents, edi_result):
            move_ids_to_cancel = set()  # Avoid duplicates
            attachments_to_unlink = self.env['ir.attachment']
            for document in documents:
                move = document.move_id
                move_result = edi_result.get(move, {})
                if move_result.get('success') is True:
                    old_attachment = document.sudo().attachment_id
                    document.sudo().write({
                        'state': 'cancelled',
                        'error': False,
                        'attachment_id': False,
                        'blocking_level': False,
                    })

                    if move.state == 'posted' and all(
                        doc.state == 'cancelled'
                        or not doc.edi_format_id._needs_web_services()
                        for doc in move.edi_document_ids
                    ):
                        # The user requested a cancellation of the EDI and it has been approved. Then, the invoice
                        # can be safely cancelled.
                        move_ids_to_cancel.add(move.id)

                    if not old_attachment.res_model or not old_attachment.res_id:
                        attachments_to_unlink |= old_attachment

                else:
                    document.write({
                        'error': move_result.get('error', False),
                        'blocking_level': move_result.get('blocking_level', DEFAULT_BLOCKING_LEVEL) if move_result.get('error') else False,
                    })

            if move_ids_to_cancel:
                invoices = self.env['account.move'].browse(list(move_ids_to_cancel))
                invoices.button_draft()
                invoices.button_cancel()

            # Attachments that are not explicitly linked to a business model could be removed because they are not
            # supposed to have any traceability from the user.
            attachments_to_unlink.sudo().unlink()

        documents = job['documents']
        if job['method_to_call']:
            method_to_call = job['method_to_call']
        else:
            method_to_call = lambda moves: {move: {'success': True} for move in moves}
        documents.edi_format_id.ensure_one()  # All account.edi.document of a job should have the same edi_format_id
        documents.move_id.company_id.ensure_one()  # All account.edi.document of a job should be from the same company
        if len(set(doc.state for doc in documents)) != 1:
            raise ValueError('All account.edi.document of a job should have the same state')

        state = documents[0].state
        documents.move_id.line_ids.flush_recordset()  # manual flush for tax details
        moves = documents.move_id
        if state == 'to_send':
            with moves._send_only_when_ready():
                edi_result = method_to_call(moves)
            _postprocess_post_edi_results(documents, edi_result)
        elif state == 'to_cancel':
            edi_result = method_to_call(moves)
            _postprocess_cancel_edi_results(documents, edi_result)

    def _process_documents_no_web_services(self):
        """ Post and cancel all the documents that don't need a web service.
        """
        jobs = self.filtered(lambda d: not d.edi_format_id._needs_web_services())._prepare_jobs()
        for job in jobs:
            self._process_job(job)

    def _process_documents_web_services(self, job_count=None, with_commit=True):
        ''' Post and cancel all the documents that need a web service.

        :param job_count:   The maximum number of jobs to process if specified.
        :param with_commit: Flag indicating a commit should be made between each job.
        :return:            The number of remaining jobs to process.
        '''
        all_jobs = self.filtered(lambda d: d.edi_format_id._needs_web_services())._prepare_jobs()
        jobs_to_process = all_jobs[0:job_count] if job_count else all_jobs

        for job in jobs_to_process:
            documents = job['documents']
            move_to_lock = documents.move_id
            attachments_potential_unlink = documents.sudo().attachment_id.filtered(lambda a: not a.res_model and not a.res_id)
            try:
                with self.env.cr.savepoint(flush=False):
                    self._cr.execute('SELECT * FROM account_edi_document WHERE id IN %s FOR UPDATE NOWAIT', [tuple(documents.ids)])
                    self._cr.execute('SELECT * FROM account_move WHERE id IN %s FOR UPDATE NOWAIT', [tuple(move_to_lock.ids)])

                    # Locks the attachments that might be unlinked
                    if attachments_potential_unlink:
                        self._cr.execute('SELECT * FROM ir_attachment WHERE id IN %s FOR UPDATE NOWAIT', [tuple(attachments_potential_unlink.ids)])

            except psycopg2.errors.LockNotAvailable:
                _logger.debug('Another transaction already locked documents rows. Cannot process documents.')
                if not with_commit:
                    raise UserError(_('This document is being sent by another process already. ')) from None
                continue
            self._process_job(job)
            if with_commit and len(jobs_to_process) > 1:
                self.env.cr.commit()

        return len(all_jobs) - len(jobs_to_process)

    @api.model
    def _cron_process_documents_web_services(self, job_count=None):
        ''' Method called by the EDI cron processing all web-services.

        :param job_count: Limit explicitely the number of web service calls. If not provided, process all.
        '''
        edi_documents = self.search([('state', 'in', ('to_send', 'to_cancel')), ('move_id.state', '=', 'posted')])
        nb_remaining_jobs = edi_documents._process_documents_web_services(job_count=job_count)

        # Mark the CRON to be triggered again asap since there is some remaining jobs to process.
        if nb_remaining_jobs > 0:
            self.env.ref('account_edi.ir_cron_edi_network')._trigger()

    def _filter_edi_attachments_for_mailing(self):
        """
        Will either return the information about the attachment of the edi document for adding the attachment in the
        mail, or the attachment id to be linked to the 'send & print' wizard.
        Can be overridden where e.g. a zip-file needs to be sent with the individual files instead of the entire zip
        IMPORTANT:
        * If the attachment's id is returned, no new attachment will be created, the existing one on the move is linked
        to the wizard (see computed attachment_ids field in mail.compose.message).
        * If the attachment's content is returned, a new one is created and linked to the wizard. Thus, when sending
        the mail (clicking on 'send & print' in the wizard), a new attachment is added to the move (see
        _action_send_mail in mail.compose.message).
        :param document: an edi document
        :return: dict {
            'attachments': tuple with the name and base64 content of the attachment}
            'attachment_ids': list containing the id of the attachment
        }
        """
        self.ensure_one()
        attachment_sudo = self.sudo().attachment_id
        if not attachment_sudo:
            return {}
        if not (attachment_sudo.res_model and attachment_sudo.res_id):
            # do not return system attachment not linked to a record
            return {}
        if len(self._context.get('active_ids', [])) > 1:
            # In mass mail mode 'attachments_ids' is removed from template values
            # as they should not be rendered
            return {'attachments': [(attachment_sudo.name, attachment_sudo.datas)]}
        return {'attachment_ids': attachment_sudo.ids}
