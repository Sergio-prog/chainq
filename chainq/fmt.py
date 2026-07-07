import os
import sys
from decimal import Decimal

BOLD = "1"
GREEN = "32"
RED = "31"


def color_enabled() -> bool:
    return sys.stdout.isatty() and "NO_COLOR" not in os.environ and os.environ.get("TERM") != "dumb"


def paint(text: str, code: str) -> str:
    if not color_enabled():
        return text
    return f"\033[{code}m{text}\033[0m"


def fmt_amount(value: object) -> str:
    d = Decimal(str(value))
    if d == 0:
        return "0"
    if abs(d) >= 1000:
        return f"{d:,.2f}"
    if abs(d) >= 1:
        return f"{d:,.4f}".rstrip("0").rstrip(".")
    frac = min(max(6 - d.adjusted() - 1, 2), 18)
    return f"{d:.{frac}f}".rstrip("0").rstrip(".")


def fmt_usd(value: object) -> str:
    d = Decimal(str(value))
    sign = "-" if d < 0 else ""
    d = abs(d)
    text = f"{sign}${d:,.2f}" if d >= 1 else f"{sign}${fmt_amount(d)}"
    return paint(text, BOLD)


def humanize_num(value: object) -> str:
    n = float(value)
    sign = "-" if n < 0 else ""
    n = abs(n)
    for suffix, div in (("T", 1e12), ("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if n >= div:
            return f"{sign}{n / div:,.2f}{suffix}"
    return f"{sign}{n:,.2f}"


def humanize_usd(value: object) -> str:
    n = humanize_num(value)
    text = f"-${n[1:]}" if n.startswith("-") else f"${n}"
    return paint(text, BOLD)


def fmt_pct(value: float | None, signed: bool = True) -> str:
    if value is None:
        return "n/a"
    if not signed:
        return f"{value:.2f}%"
    text = f"{value:+.2f}%"
    if value > 0:
        return paint(text, GREEN)
    if value < 0:
        return paint(text, RED)
    return text


def fmt_gwei(wei: int | None) -> str:
    if wei is None:
        return "n/a"
    return f"{fmt_amount(Decimal(wei) / Decimal(10**9))} gwei"


def short_addr(address: str) -> str:
    if len(address) <= 12:
        return address
    return f"{address[:6]}…{address[-4:]}"
