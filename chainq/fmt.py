from decimal import Decimal


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
    if d >= 1:
        return f"{sign}${d:,.2f}"
    return f"{sign}${fmt_amount(d)}"


def humanize_usd(value: object) -> str:
    n = float(value)
    sign = "-" if n < 0 else ""
    n = abs(n)
    for suffix, div in (("T", 1e12), ("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if n >= div:
            return f"{sign}${n / div:,.2f}{suffix}"
    return f"{sign}${n:,.2f}"


def fmt_pct(value: float | None, signed: bool = True) -> str:
    if value is None:
        return "n/a"
    return f"{value:+.2f}%" if signed else f"{value:.2f}%"


def fmt_gwei(wei: int | None) -> str:
    if wei is None:
        return "n/a"
    return f"{fmt_amount(Decimal(wei) / Decimal(10**9))} gwei"


def short_addr(address: str) -> str:
    if len(address) <= 12:
        return address
    return f"{address[:6]}…{address[-4:]}"
