"""Pembentuk ID: EAN-13 (GS1) dan nomor SAP dengan leading zero (konversi ALPHA)."""


def ean13_check_digit(first12: str) -> str:
    if len(first12) != 12 or not first12.isdigit():
        raise ValueError(f"butuh 12 digit, dapat {first12!r}")
    total = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(first12))
    return str((10 - total % 10) % 10)


def ean13(first12: str) -> str:
    return first12 + ean13_check_digit(first12)


def is_valid_ean13(code: str) -> bool:
    return len(code) == 13 and code.isdigit() and ean13_check_digit(code[:12]) == code[12]


def sap_alpha(number: int | str, length: int) -> str:
    """Nomor numerik versi internal SAP: dipad nol di kiri sampai panjang field."""
    s = str(number)
    if len(s) > length:
        raise ValueError(f"{s} lebih panjang dari {length}")
    return s.zfill(length)


def sap_posnr(item_index: int) -> str:
    """Nomor item SAP: 000010, 000020, ..."""
    return sap_alpha((item_index + 1) * 10, 6)
