import sys

from chainq.fmt import bold, dim, fmt_amount, fmt_gwei, fmt_pct, fmt_usd, green, humanize_num, humanize_usd, short_addr


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


def test_humanize_num():
    assert humanize_num(235_200_000_000) == "235.20B"
    assert humanize_num(-1_500_000) == "-1.50M"
    assert humanize_num(950) == "950.00"


def test_colors_on_tty(monkeypatch):
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm")
    assert fmt_pct(4.82) == "\033[32m+4.82%\033[0m"
    assert fmt_pct(-2.13) == "\033[31m-2.13%\033[0m"
    assert fmt_pct(0.0) == "+0.00%"
    assert fmt_pct(4.82, signed=False) == "\033[1m4.82%\033[0m"
    assert fmt_usd(1955.339) == "\033[1m$1,955.34\033[0m"
    assert humanize_usd(-1_500_000) == "\033[1m-$1.50M\033[0m"
    assert dim("24h") == "\033[2m24h\033[0m"
    assert green("3.28%") == "\033[32m3.28%\033[0m"
    assert bold("6.669 ETH") == "\033[1m6.669 ETH\033[0m"


def test_no_codes_when_piped():
    assert dim("24h") == "24h"
    assert green("3.28%") == "3.28%"
    assert bold("x") == "x"


def test_disable_colors_flag(monkeypatch):
    import chainq.fmt as fmt

    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm")
    monkeypatch.setattr(fmt, "_color_off", False)
    assert fmt.color_enabled()
    fmt.disable_colors()
    assert not fmt.color_enabled()
    assert fmt_usd(1955.339) == "$1,955.34"
    monkeypatch.setattr(fmt, "_color_off", False)


def test_dim_label(monkeypatch):
    from chainq.output import dim_label

    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm")
    assert dim_label("Base gas: 0.006 gwei") == "\033[2mBase gas:\033[0m 0.006 gwei"
    assert dim_label("  ethereum: 5.66 ETH") == "\033[2m  ethereum:\033[0m 5.66 ETH"
    assert dim_label('{"network": "base"}') == '{"network": "base"}'
    assert dim_label("\033[2mETH:\033[0m $1,776") == "\033[2mETH:\033[0m $1,776"
    assert dim_label("Base gas: \033[1m0.006 gwei\033[0m") == "\033[2mBase gas:\033[0m \033[1m0.006 gwei\033[0m"
    assert dim_label("no colon here") == "no colon here"


def test_no_color_env_wins(monkeypatch):
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setenv("NO_COLOR", "1")
    assert fmt_pct(4.82) == "+4.82%"
    assert fmt_usd(1955.339) == "$1,955.34"
