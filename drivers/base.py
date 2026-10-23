#!/usr/bin/env python3
"""
W.R.A.T. - Base Appliance Driver & Data Contract
Universal Appliance Telemetry & Diagnostics Engine
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Any, Optional, Callable, Tuple


@dataclass
class ApplianceCapabilities:
    """Flags describing what telemetry features a machine/brand supports."""
    has_live_sensors: bool = True
    has_thermal_sensors: bool = True
    has_dual_heaters: bool = False
    has_flowmeter: bool = True
    has_beverage_counters: bool = True
    has_maintenance_counters: bool = True
    has_lifetime_metrics: bool = True
    has_active_alerts: bool = True
    has_actuator_tests: bool = False


@dataclass
class ApplianceIdentification:
    """Hardware and software identity of the probed machine."""
    vendor: str
    model: str
    serial_number: str = "N/A"
    article_number: str = "N/A"
    firmware_version: str = "N/A"
    display_version: str = "N/A"
    production_date: str = "N/A"
    voltage_spec: str = "N/A"
    protocol_name: str = "N/A"
    raw_ident: str = ""


@dataclass
class SensorReading:
    """Standardized representation of a single live hardware sensor or switch."""
    id: str
    name: str
    status: str
    ok: bool = True
    badge: str = "OK"
    details: str = ""
    icon: str = "🔹"
    value: Optional[float] = None
    unit: str = ""


@dataclass
class BeverageCounter:
    """Individual beverage dispensing counter."""
    code: Any
    name: str
    count: int
    is_double: bool = False
    category: str = "Coffee"


@dataclass
class MaintenanceMetric:
    """Maintenance and hygiene cycle metric."""
    name: str
    count: int
    percent: Optional[int] = None
    warning: bool = False


@dataclass
class ApplianceTelemetry:
    """Complete snapshot of telemetry, counters, and diagnostics."""
    vendor: str
    model: str
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    identification: Optional[ApplianceIdentification] = None
    total_cups: int = 0
    total_preparations: int = 0
    beverages: List[BeverageCounter] = field(default_factory=list)
    maintenance: List[MaintenanceMetric] = field(default_factory=list)
    switches: List[Dict[str, Any]] = field(default_factory=list)
    sensors: List[Dict[str, Any]] = field(default_factory=list)
    error_counters: Dict[str, int] = field(default_factory=dict)
    operational_metrics: Dict[str, Any] = field(default_factory=dict)
    active_alerts: List[Dict[str, Any]] = field(default_factory=list)
    raw_telemetry: Dict[str, Any] = field(default_factory=dict)


class BaseApplianceDriver(ABC):
    """
    Abstract Base Class for manufacturer-specific appliance diagnostic drivers.
    Each supported brand (Jura, Nivona, Lamanti-KL, Lamanti-JN) implements this contract.
    """

    vendor: str = "Generic"
    name: str = "Generic Driver"
    supported_baudrates: List[int] = [9600]
    capabilities: ApplianceCapabilities = ApplianceCapabilities()

    @abstractmethod
    def probe(self, conn: Any) -> Optional[ApplianceIdentification]:
        """
        Send initial probe sequences to detect if the connected device
        belongs to this manufacturer/family. Returns identification if matched,
        or None if no match.
        """
        pass

    @abstractmethod
    def read_live_sensors(self, conn: Any) -> Dict[str, Any]:
        """
        Poll real-time hardware status: microswitches, thermal sensors,
        flowmeter monitors, and machine readiness.
        """
        pass

    @abstractmethod
    def read_telemetry(
        self,
        conn: Any,
        progress_cb: Optional[Callable[[float, str], None]] = None
    ) -> ApplianceTelemetry:
        """
        Perform complete extraction of appliance statistics, beverage counters,
        maintenance cycles, lifetime metrics, and historical fault counters.
        """
        pass

    def test_actuator(self, conn: Any, actuator_id: str, param: Any = None) -> bool:
        """
        Execute optional low-level technician actuator test (pump pulse, valve cycle, etc.).
        Returns True if command acknowledged and executed.
        """
        return False

    def list_supported_models(self) -> List[Tuple[str, str]]:
        """Return list of (model_code, friendly_name) supported by this driver."""
        return []
