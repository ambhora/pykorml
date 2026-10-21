# ------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2025 Jayesh Badwaik <j.badwaik@fz-juelich.de>
# ------------------------------------------------------------------------------

import pathlib

import pytest

"""
Pytest configuration and fixtures for Korml test suite.
"""


@pytest.fixture(scope="session")
def repo_root(pytestconfig) -> pathlib.Path:
    return pathlib.Path(pytestconfig.rootpath)


@pytest.fixture(scope="session")
def share_dir(repo_root: pathlib.Path) -> pathlib.Path:
    return repo_root / "share" / "korml"
