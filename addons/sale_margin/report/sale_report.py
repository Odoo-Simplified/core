# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.microkernel.ormapping import models, fields


class SaleReport(models.Model):
    _inherit = 'sale.report'

    margin = fields.Float('Margin')

    def _select_additional_fields(self):
        res = super()._select_additional_fields()
        res['margin'] = f"""SUM(l.margin
            / {self._case_value_or_one('s.currency_rate')}
            * {self._case_value_or_one('account_currency_table.rate')})
        """
        return res
