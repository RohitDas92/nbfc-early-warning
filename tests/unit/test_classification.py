import pytest

from nbfc_ews.domain.classification import asset_class_of, bucket_of


@pytest.mark.parametrize("dpd,expected", [
    (0,  "0"),
    (1,  "1-30"),
    (30, "1-30"),
    (31, "31-60"),
    (60, "31-60"),
    (61, "61-90"),
    (90,"61-90"),
    (91,"90+")
])
def test_bucket_boundaries(dpd, expected):
    assert bucket_of(dpd) == expected


def test_negative_dpd_raises():
    with pytest.raises(ValueError):
        bucket_of(-1)

@pytest.mark.parametrize("dpd,expected", [
    (0, "standard"),
    (1, "SMA0"),
    # 30, 31, 60, 61, 90, 91
    (30, "SMA0"),
    (31, "SMA1"),
    (60, "SMA1"),
    (61, "SMA2"),
    (90, "SMA2"),
    (91, "NPA"),
])
def test_asset_class_boundaries(dpd, expected):
    assert asset_class_of(dpd) == expected

def test_asset_class_rejects_negative():
    with pytest.raises(ValueError):
        asset_class_of(-1)