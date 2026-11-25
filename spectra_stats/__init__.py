"""SPECTRA Statistics Collector & Diagnostics Interrogator package."""

from spectra_stats.calibration import (
    HAS_RUST_CORE,
    _rust_core,
    __build__,
    __version__,
    _COFFEE_PRODUCT_KEYWORDS,
    _NON_COFFEE_PRODUCT_KEYWORDS,
    _NON_COFFEE_PRODUCT_CODES,
    DEFAULT_OPTICAL_BEAN_THRESHOLD,
    DEFAULT_OPTICAL_BEAN_HYSTERESIS,
    ARTICLE_MODEL_MAP,
    TWO_DIGIT_ADDRESS_EFS,
    DUAL_HEATER_EFS,
    CONFIG_DIR,
    CALIBRATION_FILE,
    is_non_coffee_product,
    get_optical_bean_threshold,
    set_optical_bean_threshold,
    reset_optical_bean_threshold,
    get_optical_bean_calibration,
    _load_calibration,
    _save_calibration,
    is_rust_core_enabled,
)
from spectra_stats.decoders import (
    decode_jura_date,
    calculate_gs1_check_digit,
    decode_jura_temperature,
    evaluate_thermoblock_status,
    evaluate_brew_unit_position,
)
from spectra_stats.live_sensors import (
    query_live_sensors,
    _last_flowmeter_samples,
    _last_bu_samples,
)
from spectra_stats.session import JuraStatsSession
from spectra_stats.diff_report import generate_eeprom_diff_report

__all__ = [
    "HAS_RUST_CORE",
    "_rust_core",
    "__build__",
    "__version__",
    "DEFAULT_OPTICAL_BEAN_THRESHOLD",
    "DEFAULT_OPTICAL_BEAN_HYSTERESIS",
    "ARTICLE_MODEL_MAP",
    "TWO_DIGIT_ADDRESS_EFS",
    "DUAL_HEATER_EFS",
    "CONFIG_DIR",
    "CALIBRATION_FILE",
    "is_non_coffee_product",
    "get_optical_bean_threshold",
    "set_optical_bean_threshold",
    "reset_optical_bean_threshold",
    "get_optical_bean_calibration",
    "_load_calibration",
    "_save_calibration",
    "decode_jura_date",
    "calculate_gs1_check_digit",
    "decode_jura_temperature",
    "evaluate_thermoblock_status",
    "evaluate_brew_unit_position",
    "query_live_sensors",
    "JuraStatsSession",
    "generate_eeprom_diff_report",
]
