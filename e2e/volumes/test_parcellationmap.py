import pytest
import siibra

from siibra import MapType
from siibra.volumes import Map
from siibra.volumes.volume import Subvolume

maps_to_compress = [
    siibra.get_map("2.9", "mni152"), # contains fragments
    siibra.get_map("difumo 64", "mni152", MapType.STATISTICAL), # contains subvolumes
]

@pytest.mark.parametrize('siibramap', maps_to_compress)
def test_compress(siibramap: Map):
    assert any([
        any(isinstance(vol, Subvolume) for vol in siibramap.volumes),
        len(siibramap.fragments) > 0,
    ])
    compressed_map = siibramap.compress()
    assert all([
        not any(isinstance(vol, Subvolume) for vol in compressed_map.volumes),
        len(compressed_map.fragments) == 0,
    ])