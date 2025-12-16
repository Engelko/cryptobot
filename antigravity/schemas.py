from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class OrderBookEntry(BaseModel):
    price: str
    size: str

class OrderBook(BaseModel):
    s: str = Field(..., description="Symbol")
    b: List[OrderBookEntry] = Field(default_factory=list, description="Bids")
    a: List[OrderBookEntry] = Field(default_factory=list, description="Asks")
    u: int = Field(..., description="Update ID")
    ts: int = Field(..., description="Timestamp")

class Trade(BaseModel):
    T: int = Field(..., description="Timestamp")
    s: str = Field(..., description="Symbol")
    S: str = Field(..., description="Side")
    v: str = Field(..., description="Volume")
    p: str = Field(..., description="Price")
