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

from ..commons import logger

from ..core.concept import AtlasConcept
from ..locations.location import Location
from ..core.parcellation import Parcellation
from ..core.region import Region
from ..core.space import Space

from ..vocabularies import REGION_ALIASES

from typing import Union, Set
from enum import Enum


class AssignmentQualification(Enum):
    EXACT = 1
    OVERLAPS = 2
    CONTAINED = 3
    CONTAINS = 4

    @property
    def verb(self):
        """
        a string that can be used as a verb in a sentence
        for producing human-readable messages.
        """
        transl = {
            'EXACT': 'coincides with',
            'OVERLAPS': 'overlaps with',
            'CONTAINED': 'is contained in',
            'CONTAINS': 'contains',
        }
        return transl[self.name]

    def invert(self):
        """
        Return a MatchPrecision object with the inverse meaning
        """
        inverses = {
            "EXACT": "EXACT",
            "OVERLAPS": "OVERLAPS",
            "CONTAINED": "CONTAINS",
            "CONTAINS": "CONTAINED",
        }
        return AssignmentQualification[inverses[self.name]]


class AnatomicalAssignment:
    """
    An assignment of an anatomical anchor to an atlas concept.
    """

    def __init__(
        self,
        assigned_structure: Union[Region, Location],
        qualification: AssignmentQualification,
        explanation: str = ""
    ):
        self.assigned_structure = assigned_structure
        self.qualification = qualification
        self.explanation = explanation.strip()

    @property
    def is_exact(self):
        return self.qualification == AssignmentQualification.EXACT

    def __str__(self):
        msg = f"{self.qualification.verb} '{self.assigned_structure}'"
        return msg if self.explanation == "" else f"{msg} ({self.explanation})."

    def invert(self):
        return AnatomicalAssignment(self.assigned_structure, self.qualification.invert(), self.explanation)

    def __lt__(self, other):
        return self.qualification.value < other.qualification.value


class AnatomicalAnchor:
    """
    Anatomical anchor to an atlas region,
    a geometric primitive in an atlas reference space,
    or both.
    """

    _MATCH_MEMO = {}

    def __init__(self, location: Location = None, region: Union[str, Region] = None, species: Union[str, Set[str]] = None):

        self._location_cached = location
        self.species = {species} if isinstance(species, str) else species
        self._assignments = {}
        self._last_matched_concept = None
        if isinstance(region, Region):
            self._regions_cached = [region]
            self._regionspec = None
        else:
            assert isinstance(region, (str, None))
            self._regions_cached = None
            self._regionspec = region

    @property
    def location(self):
        # allow to overwrite in derived classes
        return self._location_cached

    @property
    def parcellations(self):
        return list({region.root for region in self.regions})

    @property
    def space(self):
        # may be overriden by derived classes, e.g. in features.VolumeOfInterest
        if self.location is None:
            return None
        else:
            return self.location.space

    @property
    def regions(self):
        # decoding region strings is quite compute intensive, so we cache this at the class level
        if self._regions_cached is None:
            if self._regionspec is None:
                self._regions_cached = []
            else:
                if self._regionspec not in self.__class__._MATCH_MEMO:
                    # decode the region specification into a set of region objects
                    regions = {
                        r: AssignmentQualification['EXACT']
                        for species in self.species
                        for r in Parcellation.find_regions(self._regionspec, species)
                    }
                    # add more regions from possible aliases of the region spec
                    for species in self.species:
                        region_aliases = REGION_ALIASES.get(species, {}).get(self._regionspec, {})
                        for alt_species, aliases in region_aliases.items():
                            for regionspec, qualificationspec in aliases.items():
                                for r in Parcellation.find_regions(regionspec, alt_species):
                                    if r not in self._regions_cached:
                                        logger.info(f"Adding region {r.name} in {alt_species} from alias to {self._regionspec}")
                                        regions[r] = qualificationspec
                    self.__class__._MATCH_MEMO[self._regionspec] = regions
                self._regions_cached = self.__class__._MATCH_MEMO[self._regionspec]
        return self._regions_cached

    def __str__(self):
        region = "" if self._regionspec is None else str(self._regionspec)
        location = "" if self.location is None else str(self.location)
        separator = " " if min(len(region), len(location)) > 0 else ""
        return region + separator + location

    def __repr__(self):
        return self.__str__()

    def assign(self, concept: AtlasConcept):
        """
        Match this anchoring to an atlas concept.
        """
        if concept not in self._assignments:
            matches = []
            if isinstance(concept, Space):
                if self.space == concept:
                    matches.append(
                        AnatomicalAssignment(concept, AssignmentQualification.EXACT)
                    )
            elif isinstance(concept, Region):
                if any(_.matches(self._regionspec) for _ in concept):  # dramatic speedup, since decoding _regionspec is expensive
                    for r in self.regions:
                        matches.append(AnatomicalAnchor.match_regions(r, concept))
                if self.location is not None:
                    matches.append(AnatomicalAnchor.match_location_to_region(self.location, concept))
            elif isinstance(concept, Location):
                if self.location is not None:
                    matches.append(AnatomicalAnchor.match_locations(self.location, concept))
                for region in self.regions:
                    match = AnatomicalAnchor.match_location_to_region(concept, region)
                    matches.append(None if match is None else match.invert())
            self._assignments[concept] = sorted(m for m in matches if m is not None)
        self._last_matched_concept = concept \
            if len(self._assignments[concept]) > 0 \
            else None
        return self._assignments[concept]

    def matches(self, concept: AtlasConcept):
        return len(self.assign(concept)) > 0

    @classmethod
    def match_locations(cls, location1: Location, location2: Location):
        assert all(isinstance(loc, Location) for loc in [location1, location2])
        if (location1, location2) not in cls._MATCH_MEMO:
            if location1 == location2:
                res = AnatomicalAssignment(location2, AssignmentQualification.EXACT)
            elif location1.contained_in(location2):
                res = AnatomicalAssignment(location2, AssignmentQualification.CONTAINED)
            elif location1.contains(location2):
                res = AnatomicalAssignment(location2, AssignmentQualification.CONTAINS)
            elif location1.intersects(location2):
                res = AnatomicalAssignment(location2, AssignmentQualification.OVERLAPS)
            else:
                res = None
            cls._MATCH_MEMO[location1, location2] = res
        return cls._MATCH_MEMO[location1, location2]

    @classmethod
    def match_regions(cls, region1: Region, region2: Region):
        assert all(isinstance(r, Region) for r in [region1, region2])
        if (region1, region2) not in cls._MATCH_MEMO:
            if region1 == region2:
                res = AnatomicalAssignment(region2, AssignmentQualification.EXACT)
            elif region1 in region2:
                res = AnatomicalAssignment(region2, AssignmentQualification.CONTAINED)
            elif region2 in region1:
                res = AnatomicalAssignment(region2, AssignmentQualification.CONTAINS)
            else:
                res = None
            cls._MATCH_MEMO[region1, region2] = res
        return cls._MATCH_MEMO[region1, region2]

    @classmethod
    def match_location_to_region(cls, location: Location, region: Region):
        assert isinstance(location, Location)
        assert isinstance(region, Region)
        if (location, region) not in cls._MATCH_MEMO:
            # compute mask of the region
            if location.space in region.supported_spaces:
                mask = region.build_mask(space=location.space, maptype='labelled')
                mask_space = location.space
                expl = (
                    f"{location} was compared with the mask of query region "
                    f"'{region.name}' in {location.space.name}."
                )
            else:
                for space in region.supported_spaces:
                    if space.is_surface:  # siibra does not yet match locations to surface spaces
                        continue
                    mask = region.build_mask(space=space, maptype='labelled')
                    mask_space = space
                    expl = (
                        f"{location} was warped from {location.space.name} and then compared "
                        f"in this space with the mask of query region '{region.name}'."
                    )
                    if mask is not None:
                        break
            loc_warped = location.warp(mask_space)
            if mask is None:
                logger.warn(
                    f"'{region.name}' provides no mask in a space "
                    f"to which {location} can be warped."
                )
                res = None
            elif loc_warped.contained_in(mask):
                res = AnatomicalAssignment(region, AssignmentQualification.CONTAINED, expl)
            elif loc_warped.contains(mask):
                res = AnatomicalAssignment(region, AssignmentQualification.CONTAINS, expl)
            elif loc_warped.intersects(mask):
                res = AnatomicalAssignment(region, AssignmentQualification.OVERLAPS, expl)
            else:
                logger.debug(
                    f"{location} does not match mask of '{region.name}' in {mask_space.name}."
                )
                res = None
            cls._MATCH_MEMO[location, region] = res
        return cls._MATCH_MEMO[location, region]

    def represented_parcellations(self):
        """
        Return any parcellation objects that this anchor explicitly points to.
        """
        return [
            r for r in self.regions
            if isinstance(r, Parcellation)
        ]

    @property
    def last_match_result(self):
        return self._assignments.get(self._last_matched_concept)
    
    @property
    def print_last_match(self):
        return f"{self} " + ' and '.join(str(_) for _ in self.last_match_result)
