from siibra.attributes.dataproviders.volume.image import (
    intersect_ptcld_image,
    ImageProvider,
    from_nifti,
)
import siibra
from siibra.attributes.locations import PointCloud
import numpy as np
import nibabel as nib
from unittest.mock import MagicMock, patch
from itertools import product
import pytest


# TODO fix fixture
@pytest.fixture
def mocked_image_foo():
    with patch.object(ImageProvider, "get_data") as fetch_mock:
        image = ImageProvider(format="neuroglancer/precomputed", space_id="foo")
        yield image, fetch_mock


def test_insersect_ptcld_img(mocked_image_foo):
    dataobj = np.array(
        [
            [
                [0, 0, 0],
                [1, 1, 1],
                [0, 0, 0],
            ],
            [
                [0, 0, 0],
                [0, 0, 0],
                [0, 0, 0],
            ],
            [
                [0, 0, 0],
                [0, 0, 0],
                [0, 0, 0],
            ],
        ],
        dtype=np.uint8,
    )
    image, fetch_mock = mocked_image_foo
    mock_nii = nib.nifti1.Nifti1Image(dataobj, np.identity(4))

    fetch_mock.return_value = mock_nii

    ptcld = PointCloud(
        space_id="foo",
        coordinates=list(product([0, 1, 2], repeat=3)),
    )

    new_ptcld = intersect_ptcld_image(ptcld, image)

    assert new_ptcld is not ptcld
    assert new_ptcld != ptcld

    assert new_ptcld.space_id == ptcld.space_id

    assert new_ptcld.coordinates == [
        (0, 1, 0),
        (0, 1, 1),
        (0, 1, 2),
    ]


@pytest.fixture
def get_space_mock():
    mocked_space = MagicMock()
    with patch.object(siibra, "get_space", return_value=mocked_space) as mock:
        mocked_space.ID = "bar"
        yield mock


from_nifti_args = [
    ("foo", None, False),
    (None, "foo", True),
    ("foo", "foo", True),
]


@pytest.mark.parametrize("space_id, space, get_space_called", from_nifti_args)
def test_from_nifti(space_id, space, get_space_called, get_space_mock):
    result = from_nifti("http", space=space, space_id=space_id)
    assert isinstance(result, ImageProvider)
    if get_space_called:
        get_space_mock.assert_called()
        assert result.space_id == "bar"
    else:
        get_space_mock.assert_not_called()
        assert result.space_id == "foo"
