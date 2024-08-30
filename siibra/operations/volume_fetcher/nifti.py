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

from typing import TYPE_CHECKING, Tuple, List, Union
import gzip

from nibabel import Nifti1Image
import numpy as np
from nilearn.image import resample_to_img, resample_img

from .base import VolumeRetOp
from ...operations import DataOp
from ...commons.logger import siibra_tqdm
from ...attributes.dataproviders.volume.base import register_format_read

if TYPE_CHECKING:
    from ...attributes.locations import BoundingBox


class NiftiCodec(DataOp):
    input: Nifti1Image
    output: Nifti1Image
    desc = "Transforms nifti to nifti"


@register_format_read("nii", "image")
class ReadNiftiFromBytes(DataOp, VolumeRetOp):
    input: bytes
    output: Nifti1Image
    desc = "Reads bytes into nifti"
    type = "read/nifti"

    def run(self, input, **kwargs):
        assert isinstance(input, bytes)
        try:
            return Nifti1Image.from_bytes(gzip.decompress(input))
        except gzip.BadGzipFile:
            return Nifti1Image.from_bytes(input)


class NiftiMask(NiftiCodec):
    desc = "Mask nifti according to spec {kwargs."
    type = "codec/vol/mask"

    def run(
        self,
        input,
        *,
        lower_threshold: Union[None, float],
        background_value: Union[None, float, int],
        **kwargs
    ):
        assert isinstance(input, Nifti1Image)
        arr = np.asanyarray(input.dataobj)
        if lower_threshold is not None:
            return Nifti1Image(
                (arr > lower_threshold).astype("uint8"),
                input.affine,
                header=input.header,
            )
        else:
            return Nifti1Image(
                (arr != background_value).astype("uint8"),
                input.affine,
                header=input.header,
            )

    @classmethod
    def generate_specs(
        cls,
        *,
        lower_threshold: Union[float, None] = None,
        background_value: Union[float, int, None] = None,
        **kwargs
    ):
        base = super().generate_specs(**kwargs)
        return {
            **base,
            "lower_threshold": lower_threshold,
            "background_value": background_value,
        }


class NiftiExtractLabels(NiftiCodec):
    desc = "Extract a nifti with only selected labels."
    type = "codec/vol/extractlabels"

    def run(self, input, *, labels: List[int], **kwargs):
        assert isinstance(input, Nifti1Image)
        arr = np.asanyarray(input.dataobj)
        mapping = np.zeros(arr.max() + 1)
        for label in labels:
            mapping[label] = label
        return Nifti1Image(mapping[arr], input.affine, dtype=input.get_data_dtype())

    @classmethod
    def generate_specs(cls, *, labels: List[int], **kwargs):
        base = super().generate_specs(**kwargs)
        return {**base, "labels": labels}


class NiftiExtractRange(NiftiCodec):
    desc = "Extract a nifti with values only from selected range."
    type = "codec/vol/extractrange"

    def run(self, input, *, range: Tuple[float, float], **kwargs):
        assert isinstance(input, Nifti1Image)
        if not range:
            return input

        arr = np.asanyarray(input.dataobj)
        return Nifti1Image(
            (arr[np.where(range[0] < arr < range[1])]).astype(input.get_data_dtype()),
            input.affine,
        )

    @classmethod
    def generate_specs(cls, *, range: Tuple[float, float], **kwargs):
        base = super().generate_specs(**kwargs)
        return {**base, "range": range}


class NiftiExtractSubspace(NiftiCodec):
    desc = "Extract a nifti with values only from selected slice according to {kwargs."
    type = "codec/vol/extractsubspace"

    def run(self, input, *, subspace: slice, **kwargs):
        assert isinstance(input, Nifti1Image)
        s_ = tuple(slice(None) if isinstance(s, str) else s for s in subspace)
        return input.slicer[s_]

    @classmethod
    def generate_specs(cls, *, subspace: slice, **kwargs):
        base = super().generate_specs(**kwargs)
        return {**base, "subspace": subspace}

    @classmethod
    def from_subspace(cls, subspace: slice):
        return {"type": "codec/vol/extractsubspace", "subspace": subspace}


class NiftiExtractVOI(NiftiCodec):
    desc = "Extract a nifti with values only from selected volume of interest according to {kwargs."
    type = "codec/vol/extractVOI"

    def run(self, input, **kwargs):
        voi = kwargs.get("voi")
        assert isinstance(input, Nifti1Image)
        bb_vox = voi.transform(np.linalg.inv(input.affine))
        (x0, y0, z0), (x1, y1, z1) = bb_vox.minpoint, bb_vox.maxpoint
        shift = np.identity(4)
        shift[:3, -1] = bb_vox.minpoint
        result = Nifti1Image(
            dataobj=input.dataobj[x0:x1, y0:y1, z0:z1],
            affine=np.dot(input.affine, shift),
        )
        return result

    @classmethod
    def generate_specs(cls, *, voi: "BoundingBox", **kwargs):
        base = super().generate_specs(**kwargs)
        return {**base, "voi": voi}


# TODO: Morph into run + classmethod
class ResampleNifti(NiftiCodec):
    desc = "Resample a nifti according to {kwargs."
    type = "codec/vol/resample"

    def run(self, input, **kwargs):
        raise NotImplementedError

    def resample_img_to_img(
        source_img: "Nifti1Image", target_img: "Nifti1Image", interpolation: str = ""
    ) -> "Nifti1Image":
        """
        Resamples to source image to match the target image according to target's
        affine. (A wrapper of `nilearn.image.resample_to_img`.)

        Parameters
        ----------
        source_img : Nifti1Image
        target_img : Nifti1Image
        interpolation : str, Default: "nearest" if the source image is a mask otherwise "linear".
            Can be 'continuous', 'linear', or 'nearest'. Indicates the resample method.

        Returns
        -------
        Nifti1Image
        """
        interpolation = (
            "nearest"
            if np.array_equal(np.unique(source_img.dataobj), [0, 1])
            else "linear"
        )
        resampled_img = resample_to_img(
            source_img=source_img, target_img=target_img, interpolation=interpolation
        )
        return resampled_img


# TODO: Morph into run + classmethod
# TODO: take resampling out. The inputs should be provided resampled
class MergeLabelledNiftis(DataOp):
    input: List[Nifti1Image]
    output: Nifti1Image
    desc = "Merge a list of niftis according to kwargs."
    type = "codec/vol/merge"

    def run(self, input: List[Nifti1Image]):
        raise NotImplementedError

    def _resample_and_merge_niftis(
        niftis: List[Nifti1Image],
        template_affine: Union[np.ndarray, None] = None,
        labels: List[int] = [],
    ) -> Nifti1Image:
        # TODO: get header for affine and shape instead of the whole template
        assert len(niftis) > 1, "Need to supply at least two volumes to merge."
        if labels:
            assert len(niftis) == len(
                labels
            ), "Need to supply as many labels as niftis."

        if template_affine is None:
            shapes = set(nii.shape for nii in niftis)
            assert len(shapes) == 1
            shape = next(iter(shapes))
            merged_array = np.zeros(shape, dtype="int16")
            affine = niftis[0].affine
        else:
            affine = template_affine

        for i, img in siibra_tqdm(
            enumerate(niftis),
            unit="nifti",
            desc="Merging (and resmapling if necessary)",
            total=len(niftis),
            disable=len(niftis) < 3,
        ):
            if template_affine is not None:
                resampled_arr = np.asanyarray(resample_img(img, affine).dataobj)
            else:
                resampled = resample_img(img, affine, shape)
                resampled_arr = np.asanyarray(resampled.dataobj)
            nonzero_voxels = resampled_arr > 0
            if labels:
                merged_array[nonzero_voxels] = labels[i]
            else:
                merged_array[nonzero_voxels] = resampled_arr[nonzero_voxels]

        return Nifti1Image(dataobj=merged_array, affine=affine)


class IntersectNiftiWithNifti(DataOp):
    input: Tuple[Nifti1Image, Nifti1Image]
    output: Nifti1Image
    desc = """
    Get the intersection of the images' masks.

    Note
    ----
    Assumes the background is 0 for both nifti.

    Parameters
    ----------
    nii0 : Nifti1Image
    nii1 : Nifti1Image

    Returns
    -------
    Nifti1Image
        returns a mask (i.e. dtype('uint8'))
    """
    type = "codec/vol/intersectNifti"

    def run(self, input, **kwargs):
        assert all(isinstance(inpt, Nifti1Image) for inpt in input)
        nii0, nii1 = input

        arr0 = np.asanyarray(nii0.dataobj).astype("uint8")
        interpolation = kwargs.get(
            "interpolation",
            "nearest" if np.array_equal(np.unique(nii0.dataobj), [0, 1]) else "linear",
        )
        nii1_on_nii0 = resample_to_img(nii1, nii0, interpolation=interpolation)
        arr1 = np.asanyarray(nii1_on_nii0.dataobj).astype("uint8")
        elementwise_min = np.minimum(arr0, arr1)
        return Nifti1Image(dataobj=elementwise_min, affine=nii0.affine)
