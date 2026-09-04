import json
from pathlib import Path

from src.models.schemas import ToolResult

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def get_nearby_airports(airport_code: str) -> ToolResult:
    with open(DATA_DIR / "airports.json", "r", encoding="utf-8") as f:
        airports = json.load(f)

    airport = airports.get(airport_code.upper())
    if not airport:
        return ToolResult(
            success=False,
            error_type="AIRPORT_NOT_FOUND",
            error_message=f"Airport {airport_code} not found.",
            retryable=False,
        )

    return ToolResult(success=True, data=airport["nearby_airports"])
