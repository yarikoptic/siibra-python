# Copyright 2018-2024
# Institute of Neuroscience and Medicine (INM-1), Forschungszentrum Jülich GmbH

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


# Copyright 2018-2024
# Institute of Neuroscience and Medicine (INM-1), Forschungszentrum Jülich GmbH

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from typing import Generic, TypeVar, Dict, Callable
from functools import wraps

import numpy as np

from ..base import Location
from ..point import Pt
from ..pointset import PointCloud
from ..boundingbox import BBox
from ....commons_new.logger import logger

T = TypeVar("T")
_tranformers: Dict["Location", Callable] = {}


def _register_warper(location_type: Generic[T]):

    def outer(fn: Callable[[Location], Location]):

        @wraps(fn)
        def inner(loc: "Location", affine: np.ndarray, target_space: str):
            return fn(loc, affine, target_space)

        _tranformers[location_type] = inner

        return inner

    return outer


@_register_warper(Pt)
def transform_point(point: Pt, affine: np.ndarray, target_space_id: str = None) -> Pt:
    """Returns a new Point obtained by transforming the
    coordinate of this one with the given affine matrix.
    TODO this needs to maintain sigma

    Parameters
    ----------
    affine: numpy 4x4 ndarray
        affine matrix
    space: str, Space, or None
        Target reference space which is reached after applying the transform

        Note
        ----
        The consistency of this cannot be checked and is up to the user.
    """
    if point.sigma != 0:
        logger.warning("NotYetImplemented: sigma won't be retained.")
    x, y, z, h = np.dot(affine, point.homogeneous.T)
    if h != 1:
        logger.warning(f"Homogeneous coordinate is not one: {h}")
    return Pt(
        coordinate=(x / h, y / h, z / h), space_id=target_space_id
    )


@_register_warper(PointCloud)
def transform_pointcloud(ptcloud: PointCloud, affine: np.ndarray, target_space_id: str = None) -> PointCloud:
    if any(s != 0 for s in ptcloud.sigma):
        logger.warning("NotYetImplemented: sigma won't be retained.")
    return PointCloud(
        coordinates=np.dot(affine, ptcloud.homogeneous.T)[:3, :].T,
        space_id=target_space_id
    )


@_register_warper(BBox)
def transform_boundingbox(bbox: BBox, affine: np.ndarray, target_space_id: str = None) -> BBox:
    tranformed_corners = bbox.corners.transform(affine, target_space_id)
    return tranformed_corners.boundingbox


def transform(loc: Location, space_id: str) -> Location:
    return _tranformers[type(loc)](loc, space_id)
