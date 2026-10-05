import pytest

from qayem.cloud_media import byte_range


@pytest.mark.parametrize("header,expected", [
    (None, (0, 99, 200)), ("bytes=0-1", (0, 1, 206)), ("bytes=50-", (50, 99, 206)),
    ("bytes=-10", (90, 99, 206)), ("bytes=90-200", (90, 99, 206)), ("bytes=-200", (0, 99, 206)),
])
def test_browser_byte_ranges(header, expected):
    assert byte_range(header, 100) == expected


@pytest.mark.parametrize("header", ["bytes=", "bytes=5-1", "bytes=100-", "bytes=-0", "bytes=0-1,5-9", "items=0-1"])
def test_invalid_or_unsatisfiable_ranges(header):
    with pytest.raises(ValueError):
        byte_range(header, 100)
