# generated by datamodel-codegen:
#   filename:  sxplr.getAllAtlases__toSxplr__response.json
#   timestamp: 2023-12-07T15:40:42+00:00

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class SiibraAtIdModel:
    field_id: str


@dataclass
class PTAtlas:
    field_type: str
    field_id: str
    name: str
    spaces: List[SiibraAtIdModel]
    parcellations: List[SiibraAtIdModel]
    species: str


@dataclass
class Model:
    jsonrpc: str = '2.0'
    id: Optional[str] = None
    result: Optional[List[PTAtlas]] = None