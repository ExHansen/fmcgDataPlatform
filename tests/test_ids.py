import pytest

from simulators.common.ids import ean13, ean13_check_digit, is_valid_ean13, sap_alpha, sap_posnr


def test_ean13_check_digit_known_value():
    assert ean13_check_digit("400638133393") == "1"   # 4006381333931 = contoh EAN valid
    assert is_valid_ean13("4006381333931")
    assert not is_valid_ean13("4006381333932")


def test_ean13_roundtrip_and_validation():
    code = ean13("899123400001")
    assert len(code) == 13 and is_valid_ean13(code)
    with pytest.raises(ValueError):
        ean13_check_digit("123")


def test_sap_alpha_and_posnr():
    assert sap_alpha(12345, 10) == "0000012345"
    assert sap_posnr(0) == "000010" and sap_posnr(2) == "000030"
    with pytest.raises(ValueError):
        sap_alpha(10**11, 10)
