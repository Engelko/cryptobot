from decimal import Decimal, ROUND_DOWN

# Mock Map
PRECISION_MAP = {
    "BTCUSDT": 3,
    "ETHUSDT": 2,
    "SOLUSDT": 1,
    "XRPUSDT": 1,
    "ADAUSDT": 0,
    "DOGEUSDT": 0
}

def format_qty(symbol, qty_float):
    decimals = PRECISION_MAP.get(symbol, 2) # Default 2?

    # Use Decimal for floor rounding
    d = Decimal(str(qty_float))
    quantizer = Decimal("0.1") ** decimals
    if decimals == 0:
        quantizer = Decimal("1")

    rounded = d.quantize(quantizer, rounding=ROUND_DOWN)
    return f"{rounded:f}"

# Test
print(f"XRP (96.20472) -> {format_qty('XRPUSDT', 96.20472)}")
print(f"BTC (0.0012345) -> {format_qty('BTCUSDT', 0.0012345)}")
print(f"ETH (0.129) -> {format_qty('ETHUSDT', 0.129)}")
print(f"DOGE (100.5) -> {format_qty('DOGEUSDT', 100.5)}")
