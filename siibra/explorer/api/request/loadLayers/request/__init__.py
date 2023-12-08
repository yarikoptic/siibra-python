# generated by datamodel-codegen:
#   filename:  sxplr.loadLayers__toSxplr__request.json
#   timestamp: 2023-12-07T15:40:45+00:00

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

Len4num = List[float]


@dataclass
class AddableLayer:
    source: Optional[str] = None
    shader: Optional[str] = None
    transform: Optional[List[Len4num]] = None


@dataclass
class Params:
    layers: Optional[List[AddableLayer]] = None


@dataclass
class Model:
    id: Optional[str] = None
    jsonrpc: str = '2.0'
    method: str = 'sxplr.loadLayers'
    params: Optional[Params] = None