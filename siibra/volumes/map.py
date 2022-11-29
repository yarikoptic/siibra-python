# Copyright 2018-2021
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

from .volume import Volume, NiftiVolume
from .util import create_gaussian_kernel

from .. import logger, QUIET
from ..registry import REGISTRY
from ..commons import MapIndex, MapType, compare_maps, clear_name, create_key
from ..core.concept import AtlasConcept
from ..core.space import Space
from ..core.location import Point, PointSet, BoundingBox
from ..core.region import Region

import numpy as np
from tqdm import tqdm
from typing import Union, Dict

from scipy.ndimage.morphology import distance_transform_edt
from collections import defaultdict
from nibabel import Nifti1Image
from nilearn import image
import pandas as pd


class Map(AtlasConcept):

    def __init__(
        self,
        identifier: str,
        name: str,
        space_spec: dict,
        parcellation_spec: dict,
        indices: Dict[str, MapType],
        volumes: list = [],
        shortname: str = "",
        description: str = "",
        modality: str = None,
        publications: list = [],
        ebrains_ids: dict = {},
    ):
        """
        Constructs a new parcellation object.

        Parameters
        ----------
        identifier : str
            Unique identifier of the parcellation
        name : str
            Human-readable name of the parcellation
        space_spec: dict
            Specification of the space (use @id or name fields)
        parcellation_spec: str
            Specification of the parcellation (use @id or name fields)
        indices: dict
            Dictionary of indices for the brain regions.
            Keys are exact region names.
            Per region name, a list of dictionaries with fields "volume" and "label" is expected,
            where "volume" points to the index of the Volume object where this region is mapped,
            and optional "label" is the voxel label for that region.
            For contiuous / probability maps, the "label" can be null or omitted.
            For single-volume labelled maps, the "volume" can be null or omitted.
        volumes: list of Volume
            parcellation volumes
        shortname: str
            Shortform of human-readable name (optional)
        description: str
            Textual description of the parcellation
        modality  :  str or None
            Specification of the modality used for creating the parcellation
        publications: list
            List of ssociated publications, each a dictionary with "doi" and/or "citation" fields
        ebrains_ids : dict
            Identifiers of EBRAINS entities corresponding to this Parcellation.
            Key: EBRAINS KG schema, value: EBRAINS KG @id
        """
        AtlasConcept.__init__(
            self,
            identifier=identifier,
            name=name,
            shortname=shortname,
            description=description,
            publications=publications,
            ebrains_ids=ebrains_ids,
            modality=modality
        )
        assert all(
            d['volume'] in range(len(volumes))
            for v in indices.values() for d in v
        )
        self.volumes = volumes
        self._indices = {
            clear_name(k): list(map(MapIndex.from_dict, v))
            for k, v in indices.items()
        }
        # make sure the indices are unique - each map/label pair should appear at most once
        all_indices = sum(self._indices.values(), [])
        seen = set()
        duplicates = {x for x in all_indices if x in seen or seen.add(x)}
        if len(duplicates) > 0:
            logger.warn(f"Non unique indices encountered in {self}: {duplicates} ")

        self._space_spec = space_spec
        self._parcellation_spec = parcellation_spec
        for v in self.volumes:
            v._space_spec = space_spec

    def get_index(self, region: Union[str, Region]):
        """
        Returns the unique index corresponding to the specified region,
        assuming that the specification matches one unique region
        defined in this parcellation map.
        If not unique, or not defined, an exception will be thrown.
        See find_indices() for a less strict search returning all matches.
        """
        matches = self.find_indices(region)
        if len(matches) > 1:
            raise RuntimeError(
                f"The specification '{region}' matches multiple mapped "
                f"structures in {str(self)}: {list(matches.values())}"
            )
        elif len(matches) == 0:
            raise RuntimeError(
                f"The specification '{region}' does not match to any structure mapped in {self}"
            )
        else:
            return next(iter(matches))

    def find_indices(self, region: Union[str, Region]):
        """ Returns the volume/label indices in this map
        which match the given region specification"""
        regionname = region.name if isinstance(region, Region) else region
        matched_region_names = set(_.name for _ in self.parcellation.find(regionname))
        matches = matched_region_names & self._indices.keys()
        if len(matches) == 0:
            logger.warn(f"Region {regionname} not defined in {self}")
        return {
            idx: regionname
            for regionname in matches
            for idx in self._indices[regionname]
        }

    def get_region(self, label: int = None, volume: int = None, index: MapIndex = None):
        """ Returns the region mapped by the given index, if any. """
        if index is None:
            index = MapIndex(volume, label)
        matches = [
            regionname
            for regionname, indexlist in self._indices.items()
            if index in indexlist
        ]
        if len(matches) == 0:
            logger.warn(f"Index {index} not defined in {self}")
            return None
        elif len(matches) == 1:
            return self.parcellation.get_region(matches[0])
        else:
            # this should not happen, already tested in constructor
            raise RuntimeError(f"Index {index} is not unique in {self}")

    @property
    def space(self):
        for key in ["@id", "name"]:
            if key in self._space_spec:
                return REGISTRY.Space[self._space_spec[key]]
        return Space(None, "Unspecified space")

    @property
    def parcellation(self):
        for key in ["@id", "name"]:
            if key in self._parcellation_spec:
                return REGISTRY.Parcellation[self._parcellation_spec[key]]
        logger.warn(
            f"Cannot determine parcellation of {self.__class__.__name__} "
            f"{self.name} from {self._parcellation_spec}"
        )
        return None

    @property
    def labels(self):
        """
        The set of all label indices defined in this map,
        including "None" if not defined for one or more regions.
        """
        return {d.label for v in self._indices.values() for d in v}

    @property
    def maptype(self):
        if all(isinstance(_, int) for _ in self.labels):
            return MapType.LABELLED
        elif self.labels == {None}:
            return MapType.CONTINUOUS
        else:
            raise RuntimeError(
                f"Inconsistent label indices encountered in {self}"
            )

    def __len__(self):
        return len(self.volumes)

    @property
    def regions(self):
        return list(self._indices)

    def fetch(
        self,
        volume: int = None,
        resolution_mm: float = None,
        voi: BoundingBox = None,
        variant: str = None,
        format: str = None,
        index: MapIndex = None,
    ):
        """
        Fetches one particular mapped volume of this mapped.
        If there's only one map,  this is the default, otherwise the
        volume index needs to be specified, or fetch_iter() should be used
        to iterate the volumes.

        Parameters
        ----------
        volume : int
            The index of the mapped volume to be fetched.
        resolution_mm : float or None (optional)
            Physical resolution of the map, used for multi-resolution image volumes.
            If None, the smallest possible resolution will be chosen.
            If -1, the largest feasible resolution will be chosen.
        voi: VolumeOfInterest
            bounding box specification
        variant : str
            Optional specification of a specific variant to use for the maps. For example,
            fsaverage provides the 'pial', 'white matter' and 'inflated' surface variants.
        format: str
            optional specificatino of the voume format to use (e.g. "nii", "neuroglancer/precomputed")
        """
        assert len(self) > 0
        if index is not None:
            assert volume is None
            assert isinstance(index, MapIndex)
            volume = index.volume
        elif isinstance(volume, MapIndex):
            # be kind if an index is passed as the first parameter
            volume = volume.volume
        elif isinstance(volume, str):
            # be kind if a region name is passed as the first parameter
            index = self.get_index(volume)
            volume = index.volume
        if len(self) > 1:
            if volume is None:
                raise ValueError(
                    f"{self} provides {len(self)} mapped volumes, please specify which "
                    "one to fetch, or use fetch_iter() to iterate over all volumes."
                )
            else:
                if not isinstance(volume, int):
                    raise ValueError(f"Parameter 'volume' should be an integer, but '{type(volume).__name__}' was provided.")
                if volume >= len(self):
                    raise ValueError(
                        f"{self} provides only {len(self)} mapped volumes, "
                        f"but #{volume} was requested."
                    )
        result = self.volumes[volume or 0].fetch(
            resolution_mm=resolution_mm,
            format=format,
            voi=voi,
            variant=variant
        )
        if index is None or index.label is None:
            return result
        else:
            logger.info(f"Creating binary mask for label {index.label} from volume {volume}")
            return Nifti1Image(
                (np.asanyarray(result.dataobj) == index.label).astype("uint8"),
                result.affine
            )

    @property
    def affine(self):
        with QUIET:
            return self.fetch(volume=0).affine

    def fetch_iter(
        self,
        resolution_mm=None,
        voi: BoundingBox = None,
        variant: str = None,
        format: str = None
    ):
        """
        Returns an iterator to fetch all mapped volumes sequentially.

        Parameters
        ----------
        resolution_mm : float or None (optional)
            Physical resolution of the map, used for multi-resolution image volumes.
            If None, the smallest possible resolution will be chosen.
            If -1, the largest feasible resolution will be chosen.
        voi: VolumeOfInterest
            bounding box specification
        variant : str
            Optional specification of a specific variant to use for the maps. For example,
            fsaverage provides the 'pial', 'white matter' and 'inflated' surface variants.
        format: str
            optional specificatino of the voume format to use (e.g. "nii", "neuroglancer/precomputed")
        """
        return (
            self.fetch(i, resolution_mm=resolution_mm, voi=voi, variant=variant, format=format)
            for i in range(len(self))
        )

    def __iter__(self):
        return self.fetch_iter()

    def compress(self):
        """
        Converts this map into a labelled 3D parcellation map, obtained
        by taking the voxelwise maximum across the mapped volumes, and
        re-labelling regions sequentially.
        """
        result_nii = None
        voxelwise_max = None
        next_labelindex = 1
        region_indices = defaultdict(list)

        for volume in tqdm(
            range(len(self)), total=len(self), unit='maps',
            desc=f"Building compressed 3D map from {len(self)} {self.maptype.name.lower()} volumes"
        ):

            with QUIET:
                img = self.fetch(volume=volume)
            img_data = np.asanyarray(img.dataobj)

            if result_nii is None:
                result_data = np.zeros_like(img_data)
                voxelwise_max = np.zeros_like(img_data)
                result_nii = Nifti1Image(result_data, img.affine)

            if self.maptype == MapType.LABELLED:
                labels = set(np.unique(img_data)) - {0}
            else:
                labels = {None}

            for label in labels:
                region = self.get_region(label=label, volume=volume)
                region_indices[region.name].append({"volume": 0, "label": label})
                if label is None:
                    update_voxels = (img_data > voxelwise_max)
                else:
                    update_voxels = (img_data == label)
                result_data[update_voxels] = next_labelindex
                voxelwise_max[update_voxels] = img_data[update_voxels]
                next_labelindex += 1

        return Map(
            identifier=f"{create_key(self.name)}_compressed",
            name=f"{self.name} compressed",
            space_spec=self._space_spec,
            parcellation_spec=self._parcellation_spec,
            indices=region_indices,
            volumes=[
                Volume(
                    space_spec=self._space_spec,
                    providers=[NiftiVolume(result_nii)]
                )
            ]
        )

    def compute_centroids(self):
        """
        Compute a dictionary of the centroids of all regions in this map.
        """
        centroids = {}
        # list of regions sorted by mapindex
        regions = sorted(self._indices.items(), key=lambda v: min(_.volume for _ in v[1]))
        current_volume = -1
        maparr = None
        for regionname, indexlist in tqdm(regions, unit="regions", desc="Computing centroids"):
            assert len(indexlist) == 1
            index = indexlist[0]
            if index.label == 0:
                continue
            if index.volume != current_volume:
                current_volume = index.volume
                with QUIET:
                    mapimg = self.fetch(index.volume)
                maparr = np.asanyarray(mapimg.dataobj)
            if index.label is None:
                # should be a continous map then
                assert self.maptype == MapType.CONTINUOUS
                centroid_vox = np.array(np.where(maparr > 0)).mean(1)
            else:
                centroid_vox = np.array(np.where(maparr == index.label)).mean(1)
            assert regionname not in centroids
            centroids[regionname] = Point(
                np.dot(mapimg.affine, np.r_[centroid_vox, 1])[:3], space=self.space
            )
        return centroids

    def colorize(self, values: dict):
        """Colorize the map with the provided regional values.

        Parameters
        ----------
        values : dict
            Dictionary mapping regions to values

        Return
        ------
        Nifti1Image
        """

        result = None
        for volidx, vol in enumerate(self.fetch_iter()):
            img = np.asanyarray(vol.dataobj)
            maxarr = np.zeros_like(img)
            for region, value in values.items():
                index = self.get_index(region)
                if index.volume != volidx:
                    continue
                if result is None:
                    result = np.zeros_like(img)
                    affine = vol.affine
                if index.label is None:
                    updates = img > maxarr
                    result[updates] = value
                    maxarr[updates] = img[updates]
                else:
                    result[img == index.label] = value

        return Nifti1Image(result, affine)

    def sample_locations(self, regionspec, numpoints: int):
        """ Sample 3D locations inside a given region.

        The probability distribution is approximated from the region mask
        based on the squared distance transform.

        regionspec: valid region specification
            Region to be used
        numpoints: int
            Number of samples to draw

        Return
        ------
        samples : PointSet in physcial coordinates corresponding to this parcellationmap.

        """
        index = self.get_index(regionspec)
        mask = self.fetch(index=index)
        arr = np.asanyarray(mask.dataobj)
        if arr.dtype.char in np.typecodes['AllInteger']:
            # a binary mask - use distance transform to get sampling weights
            W = distance_transform_edt(np.asanyarray(mask.dataobj))**2
        else:
            # a continuous map - interpret directly as weights
            W = arr
        p = (W / W.sum()).ravel()
        XYZ_ = np.array(
            np.unravel_index(np.random.choice(len(p), numpoints, p=p), W.shape)
        ).T
        XYZ = np.dot(mask.affine, np.c_[XYZ_, np.ones(numpoints)].T)[:3, :].T
        return PointSet(XYZ, space=self.space)

    def assign(
        self,
        item: Union[Point, PointSet, Nifti1Image],
        msg=None,
        quiet=False,
        minsize_voxel=1,
        lower_threshold=0.0,
    ):
        """Assign an input image to brain regions.

        The input image is assumed to be defined in the same coordinate space
        as this parcellation map.

        Parameters
        ----------
        item: Point, PointSet, or Nifti1Image
            A spatial object defined in the same physical reference space as this
            parcellation map, which could be a point, set of points, or image.
            If it is an image, it will be resampled to the same voxel space if its affine
            transforation differs from that of the parcellation map.
            Resampling will use linear interpolation for float image types,
            otherwise nearest neighbor.
        msg: str, or None
            An optional message to be shown with the progress bar. This is
            useful if you use assign() in a loop.
        quiet: Bool, default: False
            If True, no outputs will be generated.
        minsize_voxel: int, default: 1
            Minimum voxel size of image components to be taken into account.
        lower_threshold: float, default: 0
            Lower threshold on values in the continuous map. Values smaller than
            this threshold will be excluded from the assignment computation.

        Return
        ------
        assignments : pandas Dataframe
            A table of associated regions and their scores per component found in the input image,
            or per coordinate provived.
            The scores are:
                - Value: Maximum value of the voxels in the map covered by an input coordinate or
                  input image signal component.
                - Pearson correlation coefficient between the brain region map and an input image signal
                  component (NaN for exact coordinates)
                - "Contains": Percentage of the brain region map contained in an input image signal component,
                  measured from their binarized masks as the ratio between the volume of their interesection
                  and the volume of the brain region (NaN for exact coordinates)
                - "Contained"": Percentage of an input image signal component contained in the brain region map,
                  measured from their binary masks as the ratio between the volume of their interesection
                  and the volume of the input image signal component (NaN for exact coordinates)
        components: Nifti1Image, or None
            If the input was an image, this is a labelled volume mapping the detected components
            in the input image, where pixel values correspond to the "component" column of the
            assignment table. If the input was a Point or PointSet, this is None.
        """

        components = None
        if isinstance(item, Point):
            assignments = self._assign_points(PointSet([item], item.space, sigma_mm=item.sigma), lower_threshold)
        elif isinstance(item, PointSet):
            assignments = self._assign_points(item, lower_threshold)    
        elif isinstance(item, Nifti1Image):
            assignments = self._assign_image(item, minsize_voxel, lower_threshold)
        else:
            raise RuntimeError(
                f"Items of type {item.__class__.__name__} cannot be used for region assignment."
            )

        # format assignments as pandas dataframe
        if len(assignments) == 0:
            df = pd.DataFrame(
                columns=["Component", "MapIndex", "Region", "Value", "Correlation", "IoU", "Contains", "Contained"]
            )
        else:
            result = np.array(assignments)
            ind = np.lexsort((-result[:, -1], result[:, 0]))
            df = pd.DataFrame(
                {
                    "Component": result[ind, 0].astype("int"),
                    "MapIndex": result[ind, 1].astype("int"),
                    "Region": [
                        self.get_region(volume=m, label=None).name
                        if self.maptype == MapType.CONTINUOUS
                        else self.get_region(volume=m, label=result[ind, 2]).name
                        for m in result[ind, 1]
                    ],
                    "Value": result[ind, 2],
                    "Correlation": result[ind, 6],
                    "IoU": result[ind, 3],
                    "Contains": result[ind, 5],
                    "Contained": result[ind, 4],
                }
            ).dropna(axis=1, how="all")

        if components is None:
            return df
        else:
            return df

    @staticmethod 
    def iterate_connected_components(img: Nifti1Image):
        """
        Provide an iterator over masks of connected components in the given image.
        """
        from skimage import measure
        imgdata = np.asanyarray(img.dataobj).squeeze()
        components = measure.label(imgdata > 0)
        component_labels = np.unique(components)
        assert component_labels[0] == 0
        return (
            (label, Nifti1Image((components == label).astype('uint8'), img.affine))
            for label in component_labels[1:]
        )

    def _read_voxel(self, x, y, z):
        return [
            (volume, np.asanyarray(volimg.dataobj)[x, y, z])
            for volume, volimg in enumerate(self)
        ]

    def _assign_points(self, points, lower_threshold: float):
        """
        assign a PointSet to this parcellation map.

        Parameters:
        -----------
        lower_threshold: float, default: 0
            Lower threshold on values in the continuous map. Values smaller than
            this threshold will be excluded from the assignment computation.
        """
        assignments = []

        if points.space_id != self.space.id:
            logger.info(
                f"Coordinates will be converted from {points.space.name} "
                f"to {self.space.name} space for assignment."
            )
        # convert sigma to voxel coordinates
        scaling = np.array(
            [np.linalg.norm(self.affine[:, i]) for i in range(3)]
        ).mean()
        phys2vox = np.linalg.inv(self.affine)

        for pointindex, point in enumerate(points.warp(self.space.id)):

            sigma_vox = point.sigma / scaling
            if sigma_vox < 3:
                # voxel-precise - just read out the value in the maps
                N = len(self)
                logger.info(f"Assigning coordinate {tuple(point)} to {N} maps")
                x, y, z = (np.dot(phys2vox, point.homogeneous) + 0.5).astype("int")[:3]
                vals = self._read_voxel(x, y, z)
                for volume, value in vals:
                    if value > lower_threshold:
                        assignments.append(
                            [pointindex, volume, value, np.nan, np.nan, np.nan, np.nan]
                        )
            else:
                logger.info(
                    f"Assigning uncertain coordinate {tuple(point)} to {len(self)} maps."
                )
                kernel = create_gaussian_kernel(sigma_vox, 3)
                r = int(kernel.shape[0] / 2)  # effective radius
                xyz_vox = (np.dot(phys2vox, point.homogeneous) + 0.5).astype("int")
                shift = np.identity(4)
                shift[:3, -1] = xyz_vox[:3] - r
                # build niftiimage with the Gaussian blob,
                # then recurse into this method with the image input
                W = Nifti1Image(dataobj=kernel, affine=np.dot(self.affine, shift))
                T, _ = self.assign(W, lower_threshold=lower_threshold)
                assignments.extend(
                    [
                        [pointindex, volume, value, iou, contained, contains, rho]
                        for (_, volume, _, value, rho, iou, contains, contained) in T.values
                    ]
                )
        return assignments

    def _assign_image(self, queryimg: Nifti1Image, minsize_voxel: int, lower_threshold: float):
        """
        Assign an image volume to this parcellation map.

        Parameters:
        -----------
        minsize_voxel: int, default: 1
            Minimum voxel size of image components to be taken into account.
        lower_threshold: float, default: 0
            Lower threshold on values in the continuous map. Values smaller than
            this threshold will be excluded from the assignment computation.
        """
        assignments = []

        # resample query image into this image's voxel space, if required
        if (queryimg.affine - self.affine).sum() == 0:
            queryimg = queryimg
        else:
            if issubclass(np.asanyarray(queryimg.dataobj).dtype.type, np.integer):
                interp = "nearest"
            else:
                interp = "linear"
            queryimg = image.resample_img(
                queryimg,
                target_affine=self.affine,
                target_shape=self.shape,
                interpolation=interp,
            )

        with QUIET:
            for mode, maskimg in Map.iterate_connected_components(queryimg):
                for volume, vol_img in enumerate(self):
                    vol_data = np.asanyarray(vol_img.dataobj)
                    labels = [v.label for L in self._indices.values() for v in L if v.volume==volume]
                    for label in tqdm(labels):
                        targetimg = Nifti1Image((vol_data == label).astype('uint8'), vol_img.affine)
                        scores = compare_maps(maskimg, targetimg)
                        if scores["overlap"] > 0:
                            assignments.append(
                                [mode, volume, label, scores["iou"], scores["contained"], scores["contains"], scores["correlation"]]
                            )

        return assignments


class LabelledSurface:
    """
    Represents a brain map in a surface space, with
    explicit knowledge about the region information per labelindex or channel.
    """

    def __init__(self, parcellation, space: Space):
        """
        Construct a labelled surface for the given parcellation and space.

        Parameters
        ----------
        parcellation : Parcellation
            The parcellation object used to build the map
        space : Space
            The desired template space to build the map
        """
        assert space.type == "gii"
        super().__init__(parcellation, space, MapType.LABELLED)
        self.type = "gii-label"

    def _define_maps_and_regions(self):
        self._maploaders_cached = []
        self._regions_cached = {}

        with QUIET:
            tpl = self.space.get_template()
        for meshindex, meshname in enumerate(tpl.variants):

            labelsets = [
                v
                for v in self.parcellation.get_volumes(self.space)
                if v.volume_type == self.type and v.name == meshname
            ]
            assert len(labelsets) == 1
            labels = labelsets[0].fetch()
            unmatched = []
            for labelindex in np.unique(labels):
                if labelindex != 0:
                    pindex = MapIndex(map=meshindex, label=labelindex)
                    try:
                        region = self.parcellation.get_region(pindex)
                        if labelindex > 0:
                            self._regions_cached[pindex] = region
                    except ValueError:
                        unmatched.append(pindex)
            if unmatched:
                logger.warning(
                    f"{len(unmatched)} parcellation indices in labelled surface couldn't "
                    f"be matched to region definitions in {self.parcellation.name}"
                )

            self._maploaders_cached.append(
                lambda res=None, voi=None, variant=None, name=meshname, labels=labels: {
                    **self.space.get_template(variant=variant).fetch(name=name),
                    "labels": labels,
                }
            )

    def fetch_all(self, variant=None):
        """Get the combined mesh composed of all found submeshes (e.g. both hemispheres).

        Parameters
        -----------
        variant : str
            Optional specification of variant of the maps. For example,
            fsaverage provides the 'pial', 'white matter' and 'inflated' surface variants.
        """
        vertices = np.empty((0, 3))
        faces = np.empty((0, 3))
        labels = np.empty((0))
        for surfmap in self.fetch_iter(variant=variant):
            npoints = vertices.shape[0]
            vertices = np.append(vertices, surfmap["verts"], axis=0)
            faces = np.append(faces, surfmap["faces"] + npoints, axis=0)
            labels = np.append(labels, surfmap["labels"], axis=0)

        return dict(zip(["verts", "faces", "labels"], [vertices, faces, labels]))

    def colorize(self, values: dict, name: str = None, variant: str = None):
        """Colorize the parcellation mesh with the provided regional values.

        Parameters
        ----------
        values : dict
            Dictionary mapping regions to values
        name : str
            If specified, only submeshes matching this name are included, otherwise all meshes included.
        variant : str
            Optional specification of a specific variant to use for the maps. For example,
            fsaverage provides the 'pial', 'white matter' and 'inflated' surface variants.

        Return
        ------
        List of recolored parcellation meshes, each represented as a dictionary
        with elements
        - 'verts': An Nx3 array of vertex coordinates,
        - 'faces': an Mx3 array of face definitions using row indices of the vertex array
        - 'name': Name of the of the mesh variant
        NOTE: If a specific name was requested, the single mesh is returned instead of a list.
        """

        result = []
        for mapindex, mesh in enumerate(self.fetch_iter(variant=variant)):
            if (name is not None) and (name != mesh['name']):
                continue
            cmesh = {
                'verts': mesh['verts'],
                'faces': mesh['faces'],
                'labels': np.zeros_like(mesh['labels']),
                'name': mesh['name'],
            }
            for region, value in values.items():
                try:
                    indices = self.get_index(region)
                except IndexError:
                    continue
                for index in indices:
                    if index.map == mapindex:
                        cmesh['labels'][mesh['labels'] == index.label] = value
            result.append(cmesh)

        if len(result) == 1:
            return result[0]
        else:
            return result
