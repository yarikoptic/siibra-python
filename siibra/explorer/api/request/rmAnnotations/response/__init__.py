# generated by datamodel-codegen:
#   filename:  sxplr.rmAnnotations__toSxplr__response.json
#   timestamp: 2023-12-07T15:40:38+00:00

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Model:
    jsonrpc: str = '2.0'
    id: Optional[str] = None
    result: str = 'OK'
