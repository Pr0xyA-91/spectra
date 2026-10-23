#!/usr/bin/env python3
"""
W.R.A.T. - Appliance Driver Registry & Auto-Detection Engine
"""

from typing import Dict, List, Type, Optional, Tuple, Any

from .base import (
    BaseApplianceDriver,
    ApplianceCapabilities,
    ApplianceIdentification,
    SensorReading,
    BeverageCounter,
    MaintenanceMetric,
    ApplianceTelemetry
)
from .jura.driver import JuraDriver
from .nivona.driver import NivonaDriver
from .lamanti_kl.driver import LamantiKLDriver
from .lamanti_jn.driver import LamantiJNDriver


DRIVER_REGISTRY: Dict[str, Type[BaseApplianceDriver]] = {
    "jura": JuraDriver,
    "nivona": NivonaDriver,
    "lamanti-kl": LamantiKLDriver,
    "lamanti-jn": LamantiJNDriver
}

DRIVER_DISPLAY_NAMES = {
    "auto": "⚡ Auto-Detect Connected Machine",
    "jura": "☕ Jura (Optical & Smart Connect)",
    "nivona": "☕ Nivona (CafeRomatica Series)",
    "lamanti-kl": "🏢 Lamanti-KL (Kalerm E/X/O Series)",
    "lamanti-jn": "🥤 Lamanti-JN (Jetinno JL Commercial & Vending)"
}


def list_drivers() -> List[Tuple[str, str, Type[BaseApplianceDriver]]]:
    """Return list of (vendor_key, display_name, driver_class)."""
    res = []
    for key, cls in DRIVER_REGISTRY.items():
        res.append((key, DRIVER_DISPLAY_NAMES.get(key, key.title()), cls))
    return res


def get_driver(vendor_key: str) -> BaseApplianceDriver:
    """Instantiate and return driver for specified vendor key."""
    key = vendor_key.strip().lower()
    if key in DRIVER_REGISTRY:
        return DRIVER_REGISTRY[key]()
    raise ValueError(f"Unknown appliance vendor '{vendor_key}'. Supported: {list(DRIVER_REGISTRY.keys())}")


def detect_driver(conn: Any) -> Tuple[BaseApplianceDriver, Optional[ApplianceIdentification]]:
    """
    Intelligently probe connected serial port across all supported manufacturers:
    1. Jura & Nivona via Eugster/Frismag ASCII protocol (TY:)
    2. Jura Smart Connect @-protocol
    3. Lamanti-KL via Kalerm Modbus RTU
    4. Lamanti-JN via Jetinno IO Board Serial Protocol
    """
    # 1. Probing Nivona & Jura cleartext ASCII
    try:
        # First test Nivona
        nivona_drv = NivonaDriver()
        ident = nivona_drv.probe(conn)
        if ident:
            return nivona_drv, ident
    except Exception:
        pass

    try:
        # Next test Jura
        jura_drv = JuraDriver()
        ident = jura_drv.probe(conn)
        if ident:
            return jura_drv, ident
    except Exception:
        pass

    # 2. Probing Lamanti-KL (Kalerm Modbus RTU)
    try:
        kl_drv = LamantiKLDriver()
        ident = kl_drv.probe(conn)
        if ident:
            return kl_drv, ident
    except Exception:
        pass

    # 3. Probing Lamanti-JN (Jetinno IO Protocol)
    try:
        jn_drv = LamantiJNDriver()
        ident = jn_drv.probe(conn)
        if ident:
            return jn_drv, ident
    except Exception:
        pass

    # Default fallback to Jura driver
    return JuraDriver(), None


__all__ = [
    "BaseApplianceDriver",
    "ApplianceCapabilities",
    "ApplianceIdentification",
    "SensorReading",
    "BeverageCounter",
    "MaintenanceMetric",
    "ApplianceTelemetry",
    "JuraDriver",
    "NivonaDriver",
    "LamantiKLDriver",
    "LamantiJNDriver",
    "DRIVER_REGISTRY",
    "DRIVER_DISPLAY_NAMES",
    "list_drivers",
    "get_driver",
    "detect_driver"
]
