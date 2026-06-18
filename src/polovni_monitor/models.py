"""Domain dataclasses."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Ad:
    """A parsed listing."""

    ad_id: str
    url: str
    title: str | None = None
    price: int | None = None  # EUR
    year: int | None = None
    mileage: int | None = None  # km
    fuel: str | None = None
    transmission: str | None = None
    description: str = ""
