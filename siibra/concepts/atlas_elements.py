from dataclasses import dataclass

from .attribute_collection import AttributeCollection
from ..descriptions import (
    Name,
    SpeciesSpec,
    ID as _ID
)

MUSTHAVE_ATTRIBUTES = {Name, _ID, SpeciesSpec}


@dataclass
class AtlasElement(AttributeCollection):
    schema: str = "siibra/atlas_element/v0.1"

    def __post_init__(self):
        attr_types = set(map(type, self.attributes))
        assert all(
            musthave in attr_types for musthave in MUSTHAVE_ATTRIBUTES
        ), f"An AtlasElement must have {[attr_type.__name__ for attr_type in MUSTHAVE_ATTRIBUTES]} attributes."

    @property
    def name(self):
        return self._get(Name).value

    @property
    def ID(self):
        return self._get(_ID).value

    @property
    def species(self):
        return self._get(SpeciesSpec).value
