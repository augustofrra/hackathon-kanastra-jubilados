from decimal import Decimal


def decimal_br(value: Decimal, places: int = 2) -> str:
    return f'{value:,.{places}f}'.replace(',', '_').replace('.', ',').replace('_', '.')


def days_br(value: int) -> str:
    return f'{value:,}'.replace(',', '.') + (' dia' if abs(value) == 1 else ' dias')
