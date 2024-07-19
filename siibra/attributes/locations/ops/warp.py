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

import requests
from urllib.parse import quote
import json
from typing import Generic, TypeVar, Dict, Callable
from functools import wraps

import numpy as np

from ..base import Location
from ..point import Pt
from ..pointset import PointCloud
from ..boundingbox import BBox
from ....commons_new.logger import logger
from ....exceptions import SpaceWarpingFailedError

SPACEWARP_SERVER = "https://hbp-spatial-backend.apps.hbp.eu/v1"

# lookup of space identifiers to be used by SPACEWARP_SERVER
SPACEWARP_IDS = {
    "minds/core/referencespace/v1.0.0/dafcffc5-4826-4bf1-8ff6-46b8a31ff8e2": "MNI 152 ICBM 2009c Nonlinear Asymmetric",
    "minds/core/referencespace/v1.0.0/7f39f7be-445b-47c0-9791-e971c0b6d992": "MNI Colin 27",
    "minds/core/referencespace/v1.0.0/a1655b99-82f1-420f-a3c2-fe80fd4c8588": "Big Brain (Histology)",
}

T = TypeVar("T")
_warpers: Dict["Location", Callable] = {}


def _register_warper(location_type: Generic[T]):

    def outer(fn: Callable[[Location], Location]):

        @wraps(fn)
        def inner(loc: "Location", space_id: str):
            return fn(loc, space_id)

        _warpers[location_type] = inner

        return inner

    return outer


@_register_warper(Pt)
def warp_point(point: Pt, target_space_id: str) -> Pt:
    if target_space_id == point.space_id:
        return point
    if any(_id not in SPACEWARP_IDS for _id in [point.space_id, target_space_id]):
        raise ValueError(
            f"Cannot convert coordinates between {point.space_id} and {target_space_id}"
        )
    url = "{server}/transform-point?source_space={src}&target_space={tgt}&x={x}&y={y}&z={z}".format(
        server=SPACEWARP_SERVER,
        src=quote(SPACEWARP_IDS[point.space_id]),
        tgt=quote(SPACEWARP_IDS[target_space_id]),
        x=point.coordinate[0],
        y=point.coordinate[1],
        z=point.coordinate[2],
    )
    response = requests.get(url).json()
    if any(map(np.isnan, response["target_point"])):
        raise SpaceWarpingFailedError(
            f"Warping {str(point)} to {SPACEWARP_IDS[target_space_id]} resulted in 'NaN'"
        )

    return Pt(coordinate=tuple(response["target_point"]), space_id=target_space_id)


@_register_warper(PointCloud)
def warp_pointcloud(ptcloud: PointCloud, target_space_id: str) -> PointCloud:
    chunksize = 1000
    if target_space_id == ptcloud.space_id:
        return ptcloud
    if any(_id not in SPACEWARP_IDS for _id in [ptcloud.space_id, target_space_id]):
        raise ValueError(
            f"Cannot convert coordinates between {ptcloud.space_id} and {target_space_id}"
        )

    src_points = ptcloud.coordinates
    tgt_points = []
    numofpoints = len(src_points)
    if numofpoints > 10e5:
        logger.info(
            f"Warping {numofpoints} points from {ptcloud.space.name} to {SPACEWARP_IDS[target_space_id]} space"
        )
    for i0 in range(0, numofpoints, chunksize):

        i1 = min(i0 + chunksize, numofpoints)
        data = json.dumps(
            {
                "source_space": SPACEWARP_IDS[ptcloud.space_id],
                "target_space": SPACEWARP_IDS[target_space_id],
                "source_points": src_points[i0:i1],
            }
        )
        req = requests.post(
            url=f"{SPACEWARP_SERVER}/transform-points",
            headers={
                "accept": "application/json",
                "Content-Type": "application/json",
            },
            data=data,
        )
        response = req.json()
        tgt_points.extend(list(response["target_points"]))

    return PointCloud(coordinates=tuple(tgt_points), space_id=target_space_id)


@_register_warper(BBox)
def warp_boundingbox(bbox: BBox, space_id: str) -> BBox:
    corners = bbox.corners
    corners_warped = warp_pointcloud(corners, target_space_id=space_id)
    return corners_warped.boundingbox


def warp(loc: Location, space_id: str) -> Location:
    return _warpers[type(loc)](loc, space_id)
