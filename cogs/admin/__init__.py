# -*- coding: utf-8 -*-

"""
jishaku
~~~~~~~

A discord.py extension including useful tools for bot development and debugging.

:copyright: (c) 2020 Devon (Gorialis) R
:license: MIT, see LICENSE for more details.

"""

# pylint: disable=wildcard-import
from admin.cog import *  # noqa: F401
from admin.meta import *  # noqa: F401

__all__ = (
    'Jishaku',
    'JishakuBase',
    'jsk',
    'setup'
)
