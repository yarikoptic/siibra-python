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
import numpy as np
from io import BytesIO
from nibabel import GiftiImage


from ...cache import fn_call_cache, Warmup, WarmupLevel
from ...commons_new.logger import logger


REPO = "https://github.com/kwagstyl/cortical_layers_tutorial/raw/main"
PROFILES_FILE_LEFT = "data/profiles_left.npy"
THICKNESSES_FILE_LEFT = "data/thicknesses_left.npy"
MESH_FILE_LEFT = "data/gray_left_327680.surf.gii"


@Warmup.register_warmup_fn(WarmupLevel.DATA)
def get_all():
    thickness_url = f"{REPO}/{THICKNESSES_FILE_LEFT}"
    valid, boundary_depths = get_thickness(thickness_url)
    profile_url = f"{REPO}/{PROFILES_FILE_LEFT}"
    if not get_profile.check_call_in_cache(profile_url, valid):
        logger.info(
            "First request to BigBrain profiles. Preprocessing the data "
            "now. This may take a little."
        )
    profile = get_profile(profile_url, valid)

    vertices_url = f"{REPO}/{MESH_FILE_LEFT}"
    vertices = get_vertices(vertices_url, valid)

    return valid, boundary_depths, profile, vertices


@fn_call_cache
def get_thickness(url: str):
    assert url.endswith(".npy"), "Thickness URL must end with .npy"

    resp = requests.get(url)
    resp.raise_for_status()
    thickness: np.ndarray = np.load(BytesIO(resp.content)).T

    total_thickness = thickness[:, :-1].sum(
        1
    )  # last column is the computed total thickness
    valid = np.where(total_thickness > 0)[0]

    boundary_depths = np.c_[
        np.zeros_like(valid),
        (thickness[valid, :] / total_thickness[valid, None]).cumsum(1),
    ]
    boundary_depths[:, -1] = 1  # account for float calculation errors

    return valid, boundary_depths


@fn_call_cache
def get_profile(url: str, valid: np.ndarray):
    assert url.endswith(".npy"), "Profile URL must end with .npy"
    resp = requests.get(url)
    resp.raise_for_status()
    profiles_l_all: np.ndarray = np.load(BytesIO(resp.content))
    profiles = profiles_l_all[valid, :]
    return profiles


@fn_call_cache
def get_vertices(url: str, valid: np.ndarray):
    assert url.endswith(".gii"), "Vertices URL must end with .gii"
    resp = requests.get(url)
    resp.raise_for_status()
    mesh = GiftiImage.from_bytes(resp.content)
    mesh_vertices: np.ndarray = mesh.darrays[0].data
    vertices = mesh_vertices[valid, :]
    return vertices
