"""Tests for the ``start{model,api,service,interface}`` scaffolding
management commands.

Regression coverage for the bug described in ``CHANGELOG.md``: ``startapi``/
``startservice``/``startinterface`` used to write a stub importing from
``gando.architectures.*`` -- a module path from the pre-2.x nested package
layout that no longer exists in the current flat layout. Every developer
running one of these commands got an immediately broken (``ModuleNotFound
Error``-on-import) stub.
"""

import shutil
import uuid
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import call_command


@pytest.fixture
def scaffold_app_dir():
    """Create a throwaway "app" directory under ``settings.BASE_DIR``.

    The ``start*`` commands read ``settings.BASE_DIR`` once, at import time,
    to build ``application_path = BASE_DIR / applabel``; that directory must
    already exist (the commands only ``touch()`` files inside it, they never
    create the app directory itself), just as it would for a real,
    already-registered Django app.
    """
    app_label = f'_scaffold_tmp_{uuid.uuid4().hex[:8]}'
    app_dir = Path(settings.BASE_DIR) / app_label
    app_dir.mkdir()
    try:
        yield app_label, app_dir
    finally:
        shutil.rmtree(app_dir, ignore_errors=True)


def test_startmodel_scaffolds_the_expected_file_tree(scaffold_app_dir):
    app_label, app_dir = scaffold_app_dir

    call_command('startmodel', applabel=app_label, modelname='Widget')

    assert (app_dir / 'models.py').exists()
    assert (app_dir / 'admin.py').exists()
    assert (app_dir / 'urls.py').exists()
    assert (app_dir / 'repo' / 'models' / '__widget.py').exists()
    assert (app_dir / 'repo' / 'admin' / '__widget.py').exists()
    assert (app_dir / 'repo' / 'schemas' / 'models' / '__widget.py').exists()


def test_startapi_scaffolds_a_stub_importing_the_real_flat_layout(scaffold_app_dir):
    """Regression: the generated stub must import from ``gando.apis``, not
    the nonexistent pre-2.x ``gando.architectures.apis``."""
    app_label, app_dir = scaffold_app_dir

    call_command('startapi', applabel=app_label, apiname='Widget')

    stub = app_dir / 'repo' / 'apis' / '__widget.py'
    assert stub.exists()
    content = stub.read_text()
    assert 'from gando.apis import BaseAPI' in content
    assert 'gando.architectures' not in content


def test_startservice_scaffolds_a_stub_importing_the_real_flat_layout(scaffold_app_dir):
    app_label, app_dir = scaffold_app_dir

    call_command('startservice', applabel=app_label, servicename='Widget')

    stub = app_dir / 'repo' / 'services' / 'widget.py'
    assert stub.exists()
    content = stub.read_text()
    assert 'from gando.services import BaseService' in content
    assert 'gando.architectures' not in content


def test_startinterface_scaffolds_a_stub_importing_the_real_flat_layout(scaffold_app_dir):
    app_label, app_dir = scaffold_app_dir

    call_command('startinterface', applabel=app_label, interfacename='Widget')

    stub = app_dir / 'repo' / 'interfaces' / 'widget.py'
    assert stub.exists()
    content = stub.read_text()
    assert 'from gando.interfaces import BaseInterface' in content
    assert 'gando.architectures' not in content


def test_startmodel_requires_applabel_and_modelname(scaffold_app_dir):
    from django.core.management.base import CommandError

    app_label, _ = scaffold_app_dir
    with pytest.raises(CommandError):
        call_command('startmodel', applabel=app_label, modelname=None)
