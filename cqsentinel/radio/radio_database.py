"""
Ham Radio Database for Hamlib

Comprehensive database of amateur radio transceivers with their
Hamlib model IDs, organized by manufacturer.

Updated from Hamlib documentation and common contest radios.
"""

from typing import Dict, List, Tuple, Optional


# Radio database: {Make: {Model: (hamlib_id, default_civ_address, notes)}}
RADIO_DATABASE = {
    "Icom": {
        # HF Transceivers
        "IC-705": (3085, 0xA4, "All-mode portable transceiver, HF/VHF/UHF"),
        "IC-7300": (3073, 0x94, "HF/6m SDR transceiver, popular contest radio"),
        "IC-7610": (3078, 0x98, "HF/6m SDR with dual receiver"),
        "IC-9700": (3081, 0xA2, "VHF/UHF/1.2GHz SDR transceiver"),
        "IC-7851": (3080, 0x8E, "High-end HF/6m transceiver"),
        "IC-7850": (3080, 0x8E, "High-end HF/6m transceiver (same as IC-7851)"),
        "IC-7800": (3074, 0x6A, "Flagship HF/6m transceiver"),
        "IC-7700": (3075, 0x74, "High-performance HF/6m"),
        "IC-7600": (3067, 0x7A, "HF/6m transceiver"),
        "IC-7410": (3066, 0x80, "HF/6m compact transceiver"),
        "IC-7100": (3070, 0x88, "HF/VHF/UHF mobile"),
        "IC-706MKIIG": (3009, 0x58, "HF/VHF/UHF mobile (classic)"),

        # VHF/UHF
        "IC-9100": (3068, 0x7C, "HF/VHF/UHF/1.2GHz"),
        "IC-910H": (3010, 0x60, "VHF/UHF all-mode"),
        "IC-821H": (3003, 0x4C, "VHF/UHF all-mode (classic)"),

        # Older models still in use
        "IC-756PROIII": (3046, 0x6E, "Classic HF/6m"),
        "IC-756PROII": (3045, 0x64, "Classic HF/6m"),
        "IC-756PRO": (3044, 0x5C, "Classic HF/6m"),
        "IC-746PRO": (3023, 0x66, "HF/VHF"),
        "IC-746": (3019, 0x56, "HF/VHF"),
        "IC-736": (3017, 0x4C, "HF/VHF (classic)"),
        "IC-735": (3016, 0x04, "HF only (classic)"),
    },

    "Yaesu": {
        # Modern HF
        "FT-710 AESS": (1045, None, "Compact HF/6m transceiver"),
        "FTDX10": (1043, None, "Entry-level HF/6m"),
        "FTDX101D": (1042, None, "Mid-range HF/6m SDR"),
        "FTDX101MP": (1042, None, "High-end HF/6m SDR"),
        "FTDX5000": (1033, None, "Flagship HF/6m"),
        "FTDX3000": (1032, None, "HF/6m contest radio"),
        "FTDX1200": (1031, None, "Compact HF/6m"),

        # FT-991 series (popular for portable/contest)
        "FT-991A": (1035, None, "HF/VHF/UHF all-mode"),
        "FT-991": (1035, None, "HF/VHF/UHF all-mode (original)"),

        # Mobile
        "FT-891": (1034, None, "Compact HF mobile"),
        "FT-857D": (1018, None, "HF/VHF/UHF mobile (classic)"),
        "FT-817ND": (1020, None, "Portable QRP HF/VHF/UHF"),
        "FT-818": (1044, None, "Updated QRP HF/VHF/UHF"),

        # VHF/UHF
        "FT-991A": (1035, None, "Also VHF/UHF capable"),

        # Older models
        "FT-2000": (1028, None, "HF/6m (classic)"),
        "FT-950": (1030, None, "HF/6m"),
        "FT-920": (1013, None, "HF/6m (classic)"),
        "FT-897D": (1017, None, "HF/VHF/UHF mobile"),
    },

    "Kenwood": {
        # TS Series HF
        "TS-890S": (2047, None, "Modern HF/6m SDR flagship"),
        "TS-990S": (2045, None, "High-end HF/6m dual receiver"),
        "TS-590SG": (2033, None, "Popular HF/6m contest radio"),
        "TS-590S": (2032, None, "HF/6m (original)"),
        "TS-570S": (2031, None, "Compact HF/6m"),
        "TS-480SAT": (2029, None, "Mobile HF/6m with tuner"),
        "TS-480HX": (2028, None, "Mobile HF/6m high power"),

        # HF/VHF Combos
        "TS-2000": (2037, None, "HF/VHF/UHF all-mode"),
        "TS-2000X": (2037, None, "TS-2000 with 1.2GHz"),

        # Older classics
        "TS-950SDX": (2017, None, "Classic HF/6m"),
        "TS-870S": (2018, None, "HF/6m (classic)"),
        "TS-850S": (2016, None, "Classic contest radio"),
        "TS-790A": (2014, None, "VHF/UHF all-mode (legendary)"),
        "TS-440S": (2012, None, "HF (classic)"),
    },

    "Elecraft": {
        # K Series (very popular in contesting)
        "K4": (2050, None, "Modern SDR flagship, dual RX"),
        "K3S": (2030, None, "Updated K3, excellent performance"),
        "K3": (2029, None, "Classic contest radio, modular"),
        "KX3": (2043, None, "Portable QRP HF/VHF"),
        "KX2": (2044, None, "Ultra-portable QRP HF"),

        # Older models
        "K2": (2027, None, "QRP HF kit (classic)"),
    },

    "Yaesu (FT-DX Series)": {
        "FTDX10": (1043, None, "Entry-level HF/6m"),
        "FTDX101D": (1042, None, "Dual RX HF/6m"),
        "FTDX101MP": (1042, None, "High power dual RX"),
        "FTDX5000": (1033, None, "Flagship"),
        "FTDX3000": (1032, None, "Contest favorite"),
        "FTDX1200": (1031, None, "Compact HF/6m"),
    },

    "FlexRadio": {
        "FLEX-6700": (2028, None, "SDR with 4 RX, 2 TX"),
        "FLEX-6600": (2027, None, "SDR with 2 RX, 2 TX"),
        "FLEX-6500": (2026, None, "SDR with 2 RX, 1 TX"),
        "FLEX-6400": (2025, None, "SDR entry level"),
        "FLEX-6300": (2024, None, "Popular SDR"),
    },

    "Ten-Tec": {
        "Orion": (2020, None, "HF/6m dual RX"),
        "Orion II": (2021, None, "Updated Orion"),
        "Eagle": (2022, None, "Compact HF/6m"),
        "Omni VII": (2023, None, "Classic design"),
    },

    "Alinco": {
        "DX-SR8": (2001, None, "HF/6m compact"),
        "DX-70": (2002, None, "HF/VHF mobile"),
    },

    "Xiegu": {
        "G90": (2051, None, "Compact HF/6m QRP"),
        "X5105": (2052, None, "Portable HF QRP"),
    },
}


def get_manufacturers() -> List[str]:
    """
    Get list of radio manufacturers

    Returns:
        Sorted list of manufacturer names
    """
    return sorted(RADIO_DATABASE.keys())


def get_models_by_manufacturer(manufacturer: str) -> List[str]:
    """
    Get list of radio models for a manufacturer

    Args:
        manufacturer: Manufacturer name

    Returns:
        Sorted list of model names
    """
    if manufacturer not in RADIO_DATABASE:
        return []
    return sorted(RADIO_DATABASE[manufacturer].keys())


def get_radio_info(manufacturer: str, model: str) -> Optional[Tuple[int, Optional[int], str]]:
    """
    Get radio information

    Args:
        manufacturer: Manufacturer name
        model: Model name

    Returns:
        Tuple of (hamlib_id, default_civ_address, notes) or None if not found
    """
    if manufacturer not in RADIO_DATABASE:
        return None
    if model not in RADIO_DATABASE[manufacturer]:
        return None
    return RADIO_DATABASE[manufacturer][model]


def get_hamlib_id(manufacturer: str, model: str) -> Optional[int]:
    """
    Get Hamlib model ID for a radio

    Args:
        manufacturer: Manufacturer name
        model: Model name

    Returns:
        Hamlib model ID or None if not found
    """
    info = get_radio_info(manufacturer, model)
    return info[0] if info else None


def get_default_civ_address(manufacturer: str, model: str) -> Optional[int]:
    """
    Get default CI-V address for Icom radio

    Args:
        manufacturer: Manufacturer name
        model: Model name

    Returns:
        CI-V address (hex) or None if not applicable
    """
    info = get_radio_info(manufacturer, model)
    return info[1] if info else None


def is_icom_radio(manufacturer: str) -> bool:
    """
    Check if manufacturer is Icom (supports CI-V addressing)

    Args:
        manufacturer: Manufacturer name

    Returns:
        True if Icom
    """
    return manufacturer.upper() == "ICOM"


def search_radio(query: str) -> List[Tuple[str, str, int]]:
    """
    Search for radios by name

    Args:
        query: Search query (case-insensitive)

    Returns:
        List of (manufacturer, model, hamlib_id) tuples
    """
    results = []
    query = query.lower()

    for manufacturer, models in RADIO_DATABASE.items():
        for model, (hamlib_id, civ_addr, notes) in models.items():
            if query in model.lower() or query in manufacturer.lower():
                results.append((manufacturer, model, hamlib_id))

    return results
