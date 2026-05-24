"""Unit tests for src/utils.py"""

import os
import pathlib
from unittest.mock import patch

from src.utils import Utils


def test_get_path_returns_absolute():
    path = Utils.get_path("test.txt")
    assert os.path.isabs(path)


def test_get_path_appends_filename():
    path = Utils.get_path("images/icon.svg")
    assert path.endswith("images/icon.svg")


def test_flag_path_returns_existing_flag():
    # "us.svg" should exist in the flags directory
    path = Utils.flag_path("US")
    assert path.endswith("us.svg")
    assert pathlib.Path(path).exists()


def test_flag_path_fallback_for_unknown_code():
    path = Utils.flag_path("XX")
    assert path.endswith("icon.svg")


def test_flag_path_lowercases_code():
    path_upper = Utils.flag_path("BR")
    path_lower = Utils.flag_path("br")
    assert path_upper == path_lower
