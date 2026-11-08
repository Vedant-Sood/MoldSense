"""Neutralise spreadsheet formulas in CSV text cells (CSV/formula injection)."""

FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def spreadsheet_safe(value):
    """Prefix text that a spreadsheet would run as a formula with an apostrophe.

    Numbers, and text that parses as a number such as "-3.5", are left unchanged.
    """
    if not isinstance(value, str) or not value.startswith(FORMULA_PREFIXES):
        return value
    try:
        float(value)
        return value
    except ValueError:
        return "'" + value


def safe_row(row):
    return {key: spreadsheet_safe(value) for key, value in row.items()}
