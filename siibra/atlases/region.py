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

import anytree
import json
from typing import Iterable, Union, TYPE_CHECKING, List, Tuple
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

from ..concepts import atlas_elements
from ..attributes.descriptions import Name
from ..attributes.locations import boundingbox, PointCloud
from ..attributes.dataproviders.volume import IMAGE_FORMATS
from ..commons.string import get_spec, SPEC_TYPE, extract_uuid
from ..commons.iterable import assert_ooo
from ..commons.maps import spatial_props, create_mask
from ..commons.logger import logger
from ..commons.register_recall import RegisterRecall
from ..dataops.file_fetcher.dataproxy_fetcher import DataproxyRepository
from ..cache import fn_call_cache

if TYPE_CHECKING:
    from . import Space, ParcellationScheme
    from ..assignment.qualification import Qualification


def filter_newest(regions: List["Region"]) -> List["Region"]:
    _parcellations = {r.parcellation for r in regions}
    return [r for r in regions if r.parcellation.next_version not in _parcellations]


@fn_call_cache
def _get_region_boundingbox(parc_id: str, region_name: str, space_id: str):
    from .. import get_region

    region = get_region(parc_id, region_name)
    mask = region.fetch_regional_mask(space_id)
    if mask is None:
        raise RuntimeError(f"{parc_id} {region_name} in {space_id} has no boundingbox")
    bbox = boundingbox.from_array(mask.dataobj)
    bbox = replace(bbox, maxpoint=[v + 1.0 for v in bbox.maxpoint])
    bbox = boundingbox.BoundingBox.transform(bbox, mask.affine)
    bbox.space_id = space_id
    return bbox


class Region(atlas_elements.AtlasElement, anytree.NodeMixin):
    schema: str = "siibra/atlases/region/v0.1"

    def __hash__(self):
        return hash(self.parcellation.ID + self.name)

    def __init__(self, attributes, children):
        super().__init__(self, attributes=attributes)
        anytree.NodeMixin.__init__(self)
        self.children = children

    def __repr__(self) -> str:
        if self == self.root:
            return atlas_elements.AtlasElement.__repr__(self)
        return f"{self.__class__.__name__}({self.name!r} in {self.parcellation.name!r})"

    @property
    def parcellation(self) -> "ParcellationScheme":
        return self.root

    def tree2str(self):
        """Render region-tree as a string"""
        return "\n".join(
            "%s%s" % (pre, node.name)
            for pre, _, node in anytree.RenderTree(
                self, style=anytree.render.ContRoundStyle
            )
        )

    def __iter__(self):
        return anytree.PreOrderIter(self)

    def render_tree(self):
        """Prints the tree representation of the region"""
        print(self.tree2str())

    def find(self, regionspec: SPEC_TYPE):
        children: Iterable[Region] = (region for region in anytree.PreOrderIter(self))
        match_fn = get_spec(regionspec)
        return [
            child
            for child in children
            if any(match_fn(name.value) for name in child._finditer(Name))
        ]

    def get_centroids(self, space: Union[str, "Space", None] = None) -> "PointCloud":
        from ..attributes.locations import PointCloud

        spatialprops = self._get_spatialprops(space=space, maptype="labelled")
        return PointCloud([sp["centroid"] for sp in spatialprops], space_id=space.ID)

    def get_boundingbox(
        self, space: Union[str, "Space", None] = None
    ) -> boundingbox.BoundingBox:
        from .. import get_space, Space

        space_id = None
        if isinstance(space, str):
            space = get_space(space)
        if isinstance(space, Space):
            space_id = space.ID
        if space_id is None:
            raise RuntimeError(
                f"space must be of type str or Space. You provided {type(space).__name__}"
            )
        return _get_region_boundingbox(self.parcellation.ID, self.name, space_id)

    def find_boundingboxes(self):
        from .. import find_maps

        maps = find_maps(self.parcellation.ID)

        image_mps = [
            m for m in maps if any(format in IMAGE_FORMATS for format in m.formats)
        ]

        return_result: List[boundingbox.BoundingBox] = []
        for map in image_mps:
            try:
                return_result.append(
                    _get_region_boundingbox(
                        self.parcellation.ID, self.name, map.space_id
                    )
                )
            except Exception as e:
                print(e)
                logger.debug(
                    f"Error fetching boundingbox for {str(self)} in {str(map)}: {str(e)}"
                )
        return return_result

    def get_components(self, space: Union[str, "Space", None] = None):
        spatialprops = self._get_spatialprops(space=space, maptype="labelled")
        return [sp["volume"] for sp in spatialprops]

    def _get_spatialprops(
        self,
        space: Union[str, "Space", None] = None,
        maptype: str = "labelled",
        threshold: float = 0.0,
    ):
        mask = self.fetch_regional_mask(
            space=space, maptype=maptype, lower_threshold=threshold
        )
        _spatial_props = spatial_props(
            mask, maptype=maptype, threshold_statistical=threshold
        )
        _map = next(self._finditer_regional_maps(space, maptype=maptype))
        for prop in _spatial_props.values():
            prop["centroid"].space_id = _map.space_id
        return _spatial_props

    def _finditer_regional_maps(
        self, space: Union[str, "Space", None] = None, maptype: str = "labelled"
    ):
        from .space import Space
        from .parcellationmap import Map, VALID_MAPTYPES
        from ..assignment import string_search
        from ..factory import iter_preconfigured_ac

        assert (
            maptype in VALID_MAPTYPES
        ), f"maptypes can be in {VALID_MAPTYPES}, but you provided {maptype}"

        if isinstance(space, str):
            space = assert_ooo(list(string_search(space, Space)))

        assert space is None or isinstance(
            space, Space
        ), f"space must be str, Space or None. You provided {space}"

        for mp in iter_preconfigured_ac(Map):
            if maptype != mp.maptype:
                continue
            if space and space.ID != mp.space_id:
                continue
            if self.parcellation.ID != mp.parcellation_id:
                continue
            mapped_regions = [r for r in self if r.name in mp.regions]
            if len(mapped_regions) == 0:
                continue
            yield mp.get_filtered_map(mapped_regions)

    def find_regional_maps(
        self, space: Union[str, "Space", None] = None, maptype: str = "labelled"
    ):
        return list(self._finditer_regional_maps(space, maptype))

    def fetch_regional_map(
        self,
        space: Union[str, "Space", None] = None,
        maptype: str = "labelled",
        via_space: Union[str, "Space", None] = None,
        frmt: str = None,
    ):
        if via_space is not None:
            raise NotImplementedError
        maps = self.find_regional_maps(space=space, maptype=maptype)
        try:
            selectedmap = assert_ooo(maps)
        except AssertionError:
            if maps:
                logger.warning(
                    f"Found {len(maps)} maps matching the specs. Selecting the first."
                )
                selectedmap = maps[0]
            else:
                raise ValueError(
                    f"Found no maps matching the specs for this region., {space}"
                )

        return selectedmap.fetch(frmt=frmt)

    def fetch_regional_mask(
        self,
        space: Union[str, "Space", None] = None,
        maptype: str = "labelled",
        background_value: Union[int, float] = 0,
        lower_threshold: float = None,
        via_space: Union[str, "Space", None] = None,
        frmt: str = None,
    ):
        region_map = self.fetch_regional_map(
            space=space, maptype=maptype, via_space=via_space, frmt=frmt
        )
        if region_map is None:
            return
        return create_mask(
            region_map,
            background_value=background_value,
            lower_threshold=lower_threshold,
        )

    def get_related_regions(self):
        """
        Get assements on relations of this region to others defined on EBRAINS.

        Yields
        ------
        Qualification

        Example
        -------
        >>> region = siibra.get_region("monkey", "PG")
        >>> for assesment in region.get_related_regions():
        >>>    print(assesment)
        'PG' is homologous to 'Area PGa (IPL)'
        'PG' is homologous to 'Area PGa (IPL) left'
        'PG' is homologous to 'Area PGa (IPL) right'
        'PG' is homologous to 'Area PGa (IPL)'
        'PG' is homologous to 'Area PGa (IPL) left'
        'PG' is homologous to 'Area PGa (IPL) right'
        'PG' is homologous to 'Area PGa (IPL)'
        'PG' is homologous to 'Area PGa (IPL) right'
        'PG' is homologous to 'Area PGa (IPL) left'
        """
        yield from RegionRelationAssessments.parse_from_region(self)


_region_ebrainsref_register = RegisterRecall()


class RegionRelationAssessments:
    """
    A collection of methods on finding related regions and the quantification
    of the relationship.
    """

    ref_atlas_repo = DataproxyRepository(bucketname="reference-atlas-data")

    @classmethod
    def get_peid_from_region(cls, region: Region) -> Union[str, None]:
        """
        Given a region, obtain the Parcellation Entity ID.

        Parameters
        ----------
        region : Region

        Returns
        -------
        str
        """
        from ..attributes.descriptions import EbrainsRef

        for ebrainsref in region._finditer(EbrainsRef):
            for key, value in ebrainsref.ids.items():
                if key == "openminds/ParcellationEntity":
                    if isinstance(value, str):
                        return value
                    return value[0]
        # In some cases (e.g. Julich Brain, PE is defined on the parent leaf nodes)
        if region.parent:
            parent_peid = cls.get_peid_from_region(region.parent)
            if parent_peid:
                return parent_peid

    @staticmethod
    def parse_id_arg(_id: Union[str, List[str]]) -> List[str]:
        """
        Normalizes the ebrains id property. The ebrains id field can be either
        a str or list[str]. This method normalizes it to always be list[str].

        Parameters
        ----------
        _id: strl, list[str]

        Returns
        -------
        list[str]

        Raises
        ------
        RuntimeError
        """
        if isinstance(_id, list):
            assert all(
                isinstance(_i, str) for _i in _id
            ), "all instances of pev should be str"
        elif isinstance(_id, str):
            _id = [_id]
        else:
            raise RuntimeError("parse_pev error: arg must be either list of str or str")
        return _id

    @classmethod
    def get_object(cls, obj: str):
        """
        Gets given a object (path), loads the content and serializes to json.
        Relative to the bucket 'reference-atlas-data'.

        Parameters
        ----------
        obj: str

        Returns
        -------
        dict
        """
        return json.loads(cls.ref_atlas_repo.get(obj))

    @classmethod
    def get_snapshot_factory(cls, type_str: str):
        """
        Factory method for given type.

        Parameters
        ----------
        type_str: str

        Returns
        -------
        Callable[[str|list[str]], dict]
        """

        def get_objects(_id: Union[str, List[str]]):
            _id = cls.parse_id_arg(_id)
            with ThreadPoolExecutor() as ex:
                return list(
                    ex.map(
                        cls.get_object,
                        [f"ebrainsquery/v3/{type_str}/{_}.json" for _ in _id],
                    )
                )

        return get_objects

    @classmethod
    def yield_all_regions(cls) -> Iterable[Region]:
        from ..factory import iter_preconfigured_ac
        from . import ParcellationScheme

        for p in iter_preconfigured_ac(ParcellationScheme):
            for region in p:
                yield region

    @classmethod
    def parse_relationship_assessment(cls, src: "Region", assessment):
        """
        Given a region, and the fetched assessment json, yield
        RegionRelationAssignment object.

        Parameters
        ----------
        src: Region
        assessment: dict

        Returns
        -------
        Iterable[RegionRelationAssessments]
        """
        from ..assignment.qualification import Qualification

        overlap = assessment.get("qualitativeOverlap")
        targets = assessment.get("relationAssessment") or assessment.get("inRelationTo")
        assert len(overlap) == 1, f"should be 1&o1 overlap {len(overlap)!r} "
        (overlap,) = overlap
        for target in targets:
            target_id = extract_uuid(target)

            all_regions = list(cls.yield_all_regions())
            found_targets: List[Region] = [
                region
                for region in all_regions
                if target_id in [uuid for _, uuid in region.ebrains_ids]
            ]

            for found_target in found_targets:
                yield src, found_target, Qualification.parse_relation_assessment(
                    overlap
                )

            if "https://openminds.ebrains.eu/sands/ParcellationEntity" in target.get(
                "type"
            ):
                pev_uuids = [
                    extract_uuid(has_version)
                    for pe in cls.get_snapshot_factory("ParcellationEntity")(target_id)
                    for has_version in pe.get("hasVersion")
                ]
                for reg in all_regions:
                    reg_uuids = [
                        uuid
                        for domain, uuid in reg.ebrains_ids
                        if domain == "openminds/ParcellationEntityVersion"
                    ]
                    if any(uuid in pev_uuids for uuid in reg_uuids):
                        yield src, reg, Qualification.parse_relation_assessment(overlap)

    @classmethod
    @_region_ebrainsref_register.register("openminds/CustomAnatomicalEntity")
    def translate_cae(cls, src: "Region", _id: Union[str, List[str]]):
        """Register how CustomAnatomicalEntity should be parsed

        Parameters
        ----------
        src: Region
        _id: str|list[str]

        Returns
        -------
        Iterable[RegionRelationAssessments]
        """
        caes = cls.get_snapshot_factory("CustomAnatomicalEntity")(_id)
        for cae in caes:
            for ass in cae.get("relationAssessment", []):
                yield from cls.parse_relationship_assessment(src, ass)

    @classmethod
    @_region_ebrainsref_register.register("openminds/ParcellationEntity")
    def translate_pes(cls, src: "Region", _id: Union[str, List[str]]):
        """
        Register how ParcellationEntity should be parsed

        Parameters
        ----------
        src: Region
        _id: str|list[str]

        Returns
        -------
        Iterable[RegionRelationAssessments]
        """
        from ..assignment.qualification import Qualification

        pes = cls.get_snapshot_factory("ParcellationEntity")(_id)

        for pe in pes:
            for region in cls.yield_all_regions():
                if region is src:
                    continue
                region_peid = cls.get_peid_from_region(region)
                if region_peid and (region_peid in pe.get("id")):
                    yield src, region, Qualification.OTHER_VERSION

            # homologuous
            relations = pe.get("inRelationTo", [])
            for relation in relations:
                yield from cls.parse_relationship_assessment(src, relation)

    @classmethod
    @_region_ebrainsref_register.register("openminds/ParcellationEntityVersion")
    def translate_pevs(cls, src: "Region", _id: Union[str, List[str]]):
        """
        Register how ParcellationEntityVersion should be parsed

        Parameters
        ----------
        src: Region
        _id: str|list[str]

        Returns
        -------
        Iterable[RegionRelationAssessments]
        """
        pe_uuids = [
            uuid
            for uuid in {
                extract_uuid(pe)
                for pev in cls.get_snapshot_factory("ParcellationEntityVersion")(_id)
                for pe in pev.get("isVersionOf")
            }
        ]
        yield from cls.translate_pes(src, pe_uuids)

    @classmethod
    def parse_from_region(
        cls, region: "Region"
    ) -> Iterable[Tuple[Region, Region, "Qualification"]]:
        """
        Main entry on how related regions should be retrieved. Given a region,
        retrieves all RegionRelationAssessments

        Parameters
        ----------
        region: Region

        Returns
        -------
        Iterable[RegionRelationAssessments]
        """

        from ..attributes.descriptions import EbrainsRef

        for ebrainsref in region._finditer(EbrainsRef):
            for key, value in ebrainsref.ids.items():
                for fn in _region_ebrainsref_register.iter_fn(key):
                    yield from fn(cls, region, value)
