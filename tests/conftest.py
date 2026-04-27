from __future__ import annotations

import os
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

_TEST_TEMP_PARENT = Path(tempfile.gettempdir()) / 'easy-agent-pytest'


@pytest.fixture(scope='session', autouse=True)
def _session_temp_root() -> Path:
    root = _TEST_TEMP_PARENT / f'repo-tests-{uuid4().hex}'
    root.mkdir(parents=True, exist_ok=False)
    os.environ['TMP'] = str(root)
    os.environ['TEMP'] = str(root)
    os.environ['TMPDIR'] = str(root)
    tempfile.tempdir = str(root)
    return root


@pytest.fixture
def tmp_path(_session_temp_root: Path) -> Path:
    path = _session_temp_root / f'test-{uuid4().hex}'
    path.mkdir(parents=True, exist_ok=False)
    return path
