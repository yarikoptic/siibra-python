# Copyright 2018-2020 Institute of Neuroscience and Medicine (INM-1), Forschungszentrum Jülich GmbH

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import nibabel as nib
from nibabel.affines import apply_affine
from nibabel.spatialimages import SpatialImage
from nilearn import image
from numpy import linalg as npl
import numpy as np
from functools import lru_cache
from anytree import PreOrderIter

from . import parcellations, spaces, features, logger
from .region import construct_tree, Region
from .features.regionprops import RegionProps
from .features.feature import GlobalFeature
from .features import classes as feature_classes
from .retrieval import download_file 
from .commons import create_key,Glossary
from .config import ConfigurationRegistry
from .space import Space
from .bigbrain import BigBrainVolume

def nifti_argmax_dim4(img,dim=-1):
    """
    Given a nifti image object with four dimensions, returns a modified object
    with 3 dimensions that is obtained by taking the argmax along one of the
    four dimensions (default: the last one).
    """
    assert(len(img.shape)==4)
    assert(dim>=-1 and dim<4)
    newarr = np.asarray(img.dataobj).argmax(dim)
    return nib.Nifti1Image(
            dataobj = newarr,
            header = img.header,
            affine = img.affine )

# Some parcellation maps require special handling to be expressed as a static
# parcellation. This dictionary contains postprocessing functions for converting
# the image objects returned when loading the map of a specific parcellations,
# in order to convert them to a 3D statis map. The dictionary is indexed by the
# parcellation ids.
STATIC_MAP_HOOKS = {
        "minds/core/parcellationatlas/v1.0.0/d80fbab2-ce7f-4901-a3a2-3c8ef8a3b721": lambda img : nifti_argmax_dim4(img),
        "minds/core/parcellationatlas/v1.0.0/73f41e04-b7ee-4301-a828-4b298ad05ab8": lambda img : nifti_argmax_dim4(img),
        "minds/core/parcellationatlas/v1.0.0/141d510f-0342-4f94-ace7-c97d5f160235": lambda img : nifti_argmax_dim4(img),
        "minds/core/parcellationatlas/v1.0.0/63b5794f-79a4-4464-8dc1-b32e170f3d16": lambda img : nifti_argmax_dim4(img),
        "minds/core/parcellationatlas/v1.0.0/12fca5c5-b02c-46ce-ab9f-f12babf4c7e1": lambda img : nifti_argmax_dim4(img)
        }


class Atlas:

    def __init__(self,identifier,name):
        # Setup an empty. Use _add_space and _add_parcellation to complete
        # the setup.
        self.name = name
        self.id = identifier
        self.key = create_key(name)

        # no parcellation initialized at construction
        self.regiontree = None
        self.parcellations = [] # add with _add_parcellation
        self.spaces = [] # add with _add_space

        # nothing selected yet at construction 
        self.selected_region = None
        self.selected_parcellation = None 
        self.regionnames = None

        # this can be set to prefer thresholded continuous maps as masks
        self._threshold_continuous_map = None

    def _add_space(self, space):
        self.spaces.append(space)

    def _add_parcellation(self, parcellation, select=False):
        self.parcellations.append(parcellation)
        if self.selected_parcellation is None or select:
            self.select_parcellation(parcellation)

    def __str__(self):
        return self.name

    @staticmethod
    def from_json(obj):
        """
        Provides an object hook for the json library to construct an Atlas
        object from a json stream.
        """
        if all([ '@id' in obj, 'spaces' in obj, 'parcellations' in obj,
            obj['@id'].startswith("juelich/iav/atlas/v1.0.0") ]):
            p = Atlas(obj['@id'], obj['name'])
            for space_id in obj['spaces']:
                assert(space_id in spaces)
                p._add_space( spaces[space_id] )
            for parcellation_id in obj['parcellations']:
                assert(parcellation_id in parcellations)
                p._add_parcellation( parcellations[parcellation_id] )
            return p
        return obj

    def select_parcellation(self, parcellation):
        """
        Select a different parcellation for the atlas.

        Parameters
        ----------

        parcellation : Parcellation
            The new parcellation to be selected
        """
        parcellation_obj = parcellations[parcellation]
        if parcellation_obj not in self.parcellations:
            logger.error('The requested parcellation is not supported by the selected atlas.')
            logger.error('    Parcellation:  '+parcellation_obj.name)
            logger.error('    Atlas:         '+self.name)
            logger.error(parcellation_obj.id,self.parcellations)
            raise Exception('Invalid Parcellation')
        self.selected_parcellation = parcellation_obj
        self.regiontree = construct_tree(self.selected_parcellation)
        self.regionnames = Glossary([c.key 
            for r in self.regiontree.iterate()
            for c in r.children ])
        logger.info('Selected parcellation "{}"'.format(self.selected_parcellation))

    def get_maps(self, space : Space, tree : Region = None):
        """
        Get the volumetric maps for the selected parcellation in the requested
        template space. Note that this sometimes includes multiple Nifti
        objects. For example, the Julich-Brain atlas provides two separate
        maps, one per hemisphere.

        Parameters
        ----------
        space : template space 

        Yields
        ------
        A dictionary of nibabel Nifti objects representing the volumetric map.
        The key of each object is a string that indicates which part of the
        brain each map describes, and may be used to identify the proper
        region name. In case of Julich-Brain, for example, it is "left
        hemisphere" and "right hemisphere".
        """

        maps = {}

        if space.id not in self.selected_parcellation.maps:
            logger.error('The selected atlas parcellation is not available in the requested space.')
            logger.error('- Selected parcellation: {}'.format(self.selected_parcellation.name))
            logger.error('- Requested space: {}'.format(space))

        mapurl = self.selected_parcellation.maps[space.id]

        if not mapurl:
            logger.error('Downloading parcellation maps for the requested reference space is not yet supported.')
            logger.error('- Selected parcellation: {}'.format(self.selected_parcellation.name))
            logger.error('- Requested space: {}'.format(space))

        if type(mapurl) is dict:
            # Some maps are split across multiple files, e.g. separated per
            # hemisphere. They are then given as a dictionary, where the key
            # represents a string that allows to identify them with region name
            # labels.
            for label,url in mapurl.items():

                if url=="collect":
                    assert(space.type=="neuroglancer")
                    logger.info("This space has no complete map available. Will try to find individual area maps and aggregate them into one instead.")
                    V = BigBrainVolume(space.url)
                    maxres = V.largest_feasible_resolution()
                    logger.info('This template volume is too large to download at full resolution. Will use the largest feasible resolution of {} micron'.format(maxres))
                    mip = V.resolutions_available[maxres]['mip']
                    M = SpatialImage( 
                            np.zeros(V.volume.mip_shape(mip),dtype=int), 
                            affine=V.affine(mip) )
                    regiontree = self.regiontree if tree is None else tree
                    for region in PreOrderIter(regiontree):
                        if "maps" not in region.attrs.keys():
                            continue
                        if space.id in region.attrs["maps"].keys():
                            logger.info("Found a map for region '{}'".format(str(region)))
                            assert("labelIndex" in region.attrs.keys())
                            Vr = BigBrainVolume(region.attrs["maps"][space.id])
                            Mr0 = Vr.Image(mip)
                            Mr = image.resample_to_img(Mr0,M)
                            M.dataobj[Mr.dataobj>0] = int(region.attrs['labelIndex'])
                    maps[label] = M

                else:
                    filename = download_file(url)
                    if filename is not None:
                        maps[label] = nib.load(filename)

        else:
            filename = download_file(mapurl)
            maps[''] = nib.load(filename)

        # apply postprocessing hook, if applicable
        if self.selected_parcellation.id in STATIC_MAP_HOOKS.keys():
            hook = STATIC_MAP_HOOKS[self.selected_parcellation.id]
            for k,v in maps.items():
                maps[k] = hook(v)
        
        return maps

    def get_mask(self, space : Space):
        """
        Returns a binary mask  in the given space, where nonzero values denote
        voxels corresponding to the current region selection of the atlas. 

        WARNING: Note that for selections of subtrees of the region hierarchy, this
        might include holes if the leaf regions are not completly covering
        their parent and the parent itself has no label index in the map.

        Parameters
        ----------
        space : Space
            Template space 
        """
        # remember that some parcellations are defined with multiple / split maps
        return self._get_regionmask(space,self.selected_region,
                try_thres=self._threshold_continuous_map)

    def enable_continuous_map_thresholding(self,threshold):
        """
        Enables thresholding of continous maps with the given threshold as a
        preference of using region masks from the static parcellation. For
        example, when setting threshold to 0.2, the atlas will check if it
        finds a probability map for a selected region. If it does, it will use
        the thresholded probability map as a region mask for defining the
        region, and uses it e.g. for searching spatial features.

        Use with care, because a) continuous maps are not always available, and
        b) the value ranges of continuous maps are defined in different ways
        and require careful interpretation.
        """
        self._threshold_continuous_map = threshold

    @lru_cache(maxsize=5)
    def _get_regionmask(self,space : Space,regiontree : Region, try_thres=None ):
        """
        Returns a binary mask  in the given space, where nonzero values denote
        voxels corresponding to the union of regions in the given regiontree.

        WARNING: Note that this might include holes if the leaf regions are not
        completly covering their parent and the parent itself has no label
        index in the map.

        NOTE: Function uses lru_cache, so if called repeatedly on the same
        space it will not recompute the mask.

        Parameters
        ----------
        space : Space 
            Template space 
        regiontree : Region
            A region from the region hierarchy (could be any of the root, a
            subtree, or a leaf)
        try_thres : float or None,
            If defined, will prefere threshold continous maps for mask building, see self._threshold_continuous_map.
            We make this an explicit parameter to make lru_cache aware of using it.
        """
        logger.debug("Computing the mask for {} in {}".format(
            regiontree.name, space))
        maps = self.get_maps(space,tree=regiontree)
        mask = affine = header = None 
        for description,m in maps.items():
            D = np.array(m.dataobj)
            if mask is None: 
                # copy metadata for output mask from the first map!
                mask = np.zeros_like(D)
                affine, header = m.affine, m.header
            for r in regiontree.iterate():
                if len(maps)>1 and (description not in r.name):
                    continue
                if 'labelIndex' not in r.attrs.keys():
                    continue
                if r.attrs['labelIndex'] is None:
                    continue

                # if enabled, check for available continous maps that could be
                # thresholded instead of using the mask from the static
                # parcellation
                if try_thres is not None:
                    continuous_map = r.get_specific_map(space)
                    if continuous_map is not None:
                        logger.info('Using continuous map thresholded by {} for masking region {}.'.format(
                            try_thres, r))
                        mask[np.asarray(continuous_map.dataobj)>try_thres]=1
                        continue

                # in the default case, use the labelled area from the parcellation map
                mask[D==int(r.attrs['labelIndex'])]=1

        return nib.Nifti1Image(dataobj=mask,affine=affine,header=header)

    def get_template(self, space, resolution=None ):
        """
        Get the volumetric reference template image for the given space.

        Parameters
        ----------
        space : str
            Template space definition, given as a dictionary with an '@id' key
        resolution : float or None (Default: None)
            Request the template at a particular physical resolution. If None,
            the native resolution is used.
            Currently, this only works for the BigBrain volume.

        Yields
        ------
        A nibabel Nifti object representing the reference template, or None if not available.
        TODO Returning None is not ideal, requires to implement a test on the other side. 
        """
        if space not in self.spaces:
            logger.error('The selected atlas does not support the requested reference space.')
            logger.error('- Atlas: {}'.format(self.name))
            return None

        if space.type == 'nii':
            logger.debug('Loading template image for space {}'.format(space.name))
            filename = download_file( space.url, ziptarget=space.ziptarget )
            if filename is not None:
                return nib.load(filename)
            else:
                return None

        if space.type == 'neuroglancer':
            vol = BigBrainVolume(space.url)
            helptext = "\n".join(["{:7.0f} micron {:10.4f} GByte".format(k,v['GBytes']) 
                for k,v in vol.resolutions_available.items()])
            if resolution is None:
                maxres = vol.largest_feasible_resolution()
                logger.info('This template volume is too large to download at full resolution. Will use the largest feasible resolution of {} micron'.format(maxres))
                print(helptext)
                return vol.Image(vol.resolutions_available[maxres]['mip'])
            elif resolution in vol.resolutions_available.keys(): 
                return vol.Image(vol.resolutions_available[resolution]['mip'])

            logger.error('The requested resolution is not available. Choose one of:')
            print(helptext)
            return None

        logger.error('Downloading the template image for the requested reference space is not supported.')
        logger.error('- Requested space: {}'.format(space.name))
        return None


    def select_region(self,region):
        """
        Selects a particular region. 

        TODO test carefully for selections of branching points in the region
        hierarchy, then managing all regions under the tree. This is nontrivial
        because for incomplete parcellations, the union of all child regions
        might not represent the complete parent node in the hierarchy.

        Parameters
        ----------
        region : Region
            Region to be selected. Both a region object, as well as a region
            key (uppercase string identifier) are accepted.

        Yields
        ------
        True, if selection was successful, otherwise False.
        """
        previous_region = self.selected_region
        if isinstance(region,Region):
            # argument is already a region object - use it
            self.selected_region = region
        else:
            # try to interpret argument as the key for a region 
            selected = self.regiontree.find(region,select_uppermost=True)
            if len(selected)==1:
                self.selected_region = selected[0]
            elif len(selected)==0:
                logger.error('Cannot select region. The spec "{}" does not match any known region.'.format(region))
            else:
                logger.error('Cannot select region. The spec "{}" is not unique. It matches: {}'.format(
                    region,", ".join([s.name for s in selected])))
        if not self.selected_region == previous_region:
            logger.info('Selected region {}'.format(self.selected_region.name))
            return self.selected_region
        return None

    def clear_selection(self):
        """
        Cancels any current region selection.
        """
        self.select_region(self.regiontree)

    def region_selected(self,region):
        """
        Verifies wether a given region is part of the current selection.
        """
        return self.selected_region.includes(region)

    def coordinate_selected(self,space,coordinate):
        """
        Verifies wether a position in the given space is inside the current
        selection.

        Parameters
        ----------
        space : Space
            The template space in which the test shall be carried out
        coordinate : tuple x/y/z
            A coordinate position given in the physical space. It will be
            converted to the voxel space using the inverse affine matrix of the
            template space for the query.

        NOTE: since get_mask is lru-cached, this is not necessary slow
        """
        assert(space in self.spaces)
        # transform physical coordinates to voxel coordinates for the query
        mask = self.get_mask(space)
        voxel = (apply_affine(npl.inv(mask.affine),coordinate)+.5).astype(int)
        if np.any(voxel>=mask.dataobj.shape):
            return False
        if mask.dataobj[voxel[0],voxel[1],voxel[2]]==0:
            return False
        return True

    def query_data(self,modality,**kwargs):
        """
        Query data features for the currently selected region(s) by modality. 
        See brainscapes.features.modalities for available modalities.
        """
        hits = []

        if modality not in features.extractor_types.modalities:
            logger.error("Cannot query features - no feature extractor known "\
                    "for feature type {}.".format(modality))
            return hits

        # make sure that a region is selected when expected
        local_query = GlobalFeature not in feature_classes[modality].__bases__ 
        if local_query and not self.selected_region:
            logger.error("For non-global feature types "\
                    "select a region using 'select_region' to query data.")
            return hits

        for cls in features.extractor_types[modality]:
            if modality=='GeneExpression':
                extractor = cls(kwargs['gene'])
            else:
                extractor = cls()
            hits.extend(extractor.pick_selection(self))

        return hits

    def regionprops(self,space, include_children=False):
        """
        Extracts spatial properties of the currently selected region.
        Optionally, separate spatial properties of all child regions are
        computed.

        Parameters
        ----------
        space : Space
            The template space in which the spatial properties shall be
            computed.
        include_children : Boolean (default: False)
            If true, compute the properties of all children in the region
            hierarchy as well.

        Yields
        ------
        List of RegionProps objects (refer to RegionProp.regionname for
        identification of each)
        """
        result = []
        result.append ( RegionProps(self,space) )
        if include_children:
            parentregion = self.selected_region
            for region in self.selected_region.descendants:
                self.select_region(region)
                result.append ( RegionProps(self,space) )
            self.select_region(parentregion)
        return result



REGISTRY = ConfigurationRegistry('atlases', Atlas)

if __name__ == '__main__':

    atlas = REGISTRY.MULTILEVEL_HUMAN_ATLAS

    print(atlas.regiontree)
    print('*******************************')
    print(atlas.regiontree.find('hOc1'))
    print('*******************************')
    print(atlas.regiontree.find('LB (Amygdala) - left hemisphere'))
    print('******************************')
    print(atlas.regiontree.find('Ch 123 (Basal Forebrain) - left hemisphere'))
