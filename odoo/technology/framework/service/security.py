# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import odoo
import odoo.exceptions
from ...utils import encrypt as _encrypt

def check(db, uid, passwd, registry):
    res_users = registry(db)['res.users']
    return res_users.check(db, uid, passwd)

def compute_session_token(session, env):
    self = env['res.users'].browse(session.uid)
    return self._compute_session_token(session.sid)

def check_session(session, env, request=None):
    self = env['res.users'].browse(session.uid)
    expected = self._compute_session_token(session.sid)
    if expected and _encrypt.consteq(expected, session.session_token):
        if request:
            env['res.device.log']._update_device(request)
        return True
    return False
