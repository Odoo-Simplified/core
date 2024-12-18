from odoo.microkernel.ormapping import models
from odoo.microkernel import api

class ResCompany(models.Model):
    _inherit = 'res.company'

    @api.model
    def _load_pos_data_fields(self, config_id):
        return super()._load_pos_data_fields(config_id) + ['l10n_es_tbai_is_enabled']
