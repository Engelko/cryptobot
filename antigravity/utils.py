from typing import Any, Optional
from antigravity.logging import get_logger

logger = get_logger("utils")

def safe_float(value: Any, default: float = 0.0) -> float:
    """
    Safely convert a value to float, handling empty strings and None.
    """
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        logger.debug("safe_float_conversion_failed", value=value, default=default)
        return default
