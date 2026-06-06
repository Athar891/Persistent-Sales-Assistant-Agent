"""Product catalog schema (also the shape of GET /catalog's data)."""

from pydantic import BaseModel


class Plan(BaseModel):
    name: str
    price: str
    features: list[str]


class Catalog(BaseModel):
    plans: list[Plan]
