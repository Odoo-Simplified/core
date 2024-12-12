# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import _
from odoo.microkernel.ormapping import models
from odoo.microkernel import api

class Channel(models.Model):
    _inherit = 'discuss.channel'

    def execute_command_help(self, **kwargs):
        super().execute_command_help(**kwargs)
        self.env['mail.bot']._apply_logic(self, kwargs, command="help")  # kwargs are not usefull but...
