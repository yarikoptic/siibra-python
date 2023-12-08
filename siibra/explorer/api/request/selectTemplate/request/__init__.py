# generated by datamodel-codegen:
#   filename:  sxplr.selectTemplate__toSxplr__request.json
#   timestamp: 2023-12-07T15:40:39+00:00

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class AtId:
    field_id: Optional[str] = None


@dataclass
class Model:
    id: Optional[str] = None
    jsonrpc: str = '2.0'
    method: str = 'sxplr.selectTemplate'
    params: Optional[AtId] = None