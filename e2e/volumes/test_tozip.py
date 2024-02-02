import pytest
import siibra

from siibra import MapType
from siibra.volumes import Map

from zipfile import ZipFile
import os


volumes_to_extract = [
    siibra.features.cellular.CellbodyStainedSection._get_instances()[0],
    siibra.features.cellular.CellbodyStainedSection._get_instances()[5],
    siibra.features.cellular.CellBodyStainedVolumeOfInterest._get_instances()[1],
    siibra.features.macrostructural.BlockfaceVolumeOfInterest._get_instances()[0],
    siibra.get_template('bigbrain'),
    siibra.get_template('mni152'),
    siibra.get_template('fsaverage6')
]


@pytest.mark.parametrize("siibramap", volumes_to_extract)
def test_volume_to_zip(siibramap: Map):
    zpname = f"{siibramap.name}.zip"
    siibramap.to_zip(zpname)
    with ZipFile(zpname) as zf:
        filenames = [info.filename for info in zf.filelist]
        assert "README.md" in filenames
    os.remove(zpname)


maps_to_extract = [
    siibra.get_map("julich 3", "mni152"),
    siibra.get_map("julich 2.9", "mni152"),  # contains fragments
    siibra.get_map("difumo 64", "mni152", MapType.STATISTICAL),  # contains subvolumes
]


@pytest.mark.parametrize("siibramap", maps_to_extract)
def test_map_to_zip(siibramap: Map):
    zpname = f"{siibramap.name}.zip"
    siibramap.to_zip(zpname)
    with ZipFile(zpname) as zf:
        filenames = [info.filename for info in zf.filelist]
        assert "README.md" in filenames
    os.remove(zpname)
