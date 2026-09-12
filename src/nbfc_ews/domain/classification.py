from typing import Literal

Bucket = Literal["0","1-30","31-60","61-90","90+"]
AssetClass = Literal["standard","SMA0","SMA1","SMA2","NPA"]

_BUCKETS: list[tuple[int, Bucket]] = [
    (0, "0"),
    (30, "1-30"),
    (60, "31-60"),
    (90, "61-90")
]

_BUCKET_TO_CLASS: dict[Bucket, AssetClass] = {
    "0": "standard",
    "1-30": "SMA0",
    "31-60": "SMA1",
    "61-90": "SMA2",
    "90+": "NPA"
}

def bucket_of(dpd: int) -> Bucket:
    "Maps days past due to Delinquency Bucket"

    if dpd < 0:
        raise ValueError(f"dpd cannot be negative: {dpd}")
    for upper, name in _BUCKETS:
        if dpd <= upper:
            return name
    return "90+"

def asset_class_of(dpd: int) -> AssetClass:
    """Maps days-past-dues to respective IRACP Asset Class"""
    return _BUCKET_TO_CLASS[bucket_of(dpd)]
