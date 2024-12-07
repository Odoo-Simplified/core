import typing
import tempfile
from contextlib import contextmanager

import odoo.addons
from odoo.api import Environment
if typing.TYPE_CHECKING:
    from odoo.addons.base.models.res_lang import LangData

# ----------------------------------------------------------
# File paths
# ----------------------------------------------------------
@contextmanager
def file_open_temporary_directory(env: Environment):
    """Create and return a temporary directory added to the directories `file_open` is allowed to read from.

    `file_open` will be allowed to open files within the temporary directory
    only for environments of the same transaction than `env`.
    Meaning, other transactions/requests from other users or even other databases
    won't be allowed to open files from this directory.

    Examples::

        >>> with odoo.tools.file_open_temporary_directory(self.env) as module_dir:
        ...    with zipfile.ZipFile('foo.zip', 'r') as z:
        ...        z.extract('foo/__manifest__.py', module_dir)
        ...    temporary_paths = self.env.transaction._Transaction__file_open_tmp_paths
        ...    with odoo.tools.file_open('foo/__manifest__.py', temporary_paths=temporary_paths) as f:
        ...        manifest = f.read()

    :param env: environment for which the temporary directory is created.
    :return: the absolute path to the created temporary directory
    """
    assert not env.transaction._Transaction__file_open_tmp_paths, 'Reentrancy is not implemented for this method'
    with tempfile.TemporaryDirectory() as module_dir:
        try:
            env.transaction._Transaction__file_open_tmp_paths = (module_dir,)
            yield module_dir
        finally:
            env.transaction._Transaction__file_open_tmp_paths = ()