from chainq.fmt import fmt_amount, fmt_gwei, fmt_pct, fmt_usd, humanize_usd, short_addr


def test_fmt_amount():
    assert fmt_amount(0) == "0"
    assert fmt_amount("1234.5678") == "1,234.57"
    assert fmt_amount("1.5") == "1.5"
    assert fmt_amount("0.000123456") == "0.000123456"
    assert fmt_amount("30.57012") == "30.5701"


def test_fmt_usd():
    assert fmt_usd(1955.339) == "$1,955.34"
    assert fmt_usd(0.00012345) == "$0.00012345"
    assert fmt_usd(-12.5) == "-$12.50"


def test_humanize_usd():
    assert humanize_usd(235_200_000_000) == "$235.20B"
    assert humanize_usd(1_500_000) == "$1.50M"
    assert humanize_usd(950) == "$950.00"


def test_fmt_pct():
    assert fmt_pct(None) == "n/a"
    assert fmt_pct(-2.13) == "-2.13%"
    assert fmt_pct(1.0) == "+1.00%"


def test_fmt_gwei():
    assert fmt_gwei(1_500_000_000) == "1.5 gwei"
    assert fmt_gwei(None) == "n/a"


def test_short_addr():
    assert short_addr("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045") == "0xd8dA…6045"
    assert short_addr("short") == "short"
