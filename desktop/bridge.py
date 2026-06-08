"""
Stable pywebview API entry point for window.pywebview.api.* calls.

The implementation is split across domain mixins in desktop.bridge_api.
"""

from __future__ import annotations

import time

from desktop.bridge_api.base import BaseBridgeMixin
from desktop.bridge_api.companies import CompanyBridgeMixin
from desktop.bridge_api.energy import EnergyBridgeMixin
from desktop.bridge_api.refresh import RefreshBridgeMixin
from desktop.bridge_api.status import StatusBridgeMixin


class CVMBridge(
    BaseBridgeMixin,
    CompanyBridgeMixin,
    RefreshBridgeMixin,
    StatusBridgeMixin,
    EnergyBridgeMixin,
):
    pass
