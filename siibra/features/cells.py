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

import numpy as np
from gitlab import Gitlab
import gzip
import nibabel as nib
import json
import os

from .feature import RegionalFeature,SpatialFeature
from .query import FeatureQuery
from ..commons import HAVE_PYPLOT,HAVE_PLOTTING
from .. import logger,spaces
from ..retrieval import GitlabQuery,OwncloudQuery #cached_gitlab_query,cached_get,LazyLoader


class CorticalCellDistribution(RegionalFeature):
    """
    Represents a cortical cell distribution dataset. 
    Implements lazy and cached loading of actual data. 
    """

    def __init__(self, regionspec, cells, query, folder):

        _,section_id,patch_id = folder.split("/")
        RegionalFeature.__init__(self,regionspec,f"{query.server}-{query.share}")
        self.cells = cells
        self._query = query

        # construct lazy data loaders
        self._info_loader = query.build_lazyloader(
            "info.txt",folder,
            lambda b:dict(l.split(' ') for l in b.decode('utf8').strip().split("\n")) )
        self._image_loader = query.build_lazyloader(
            "image.nii.gz",folder,
            lambda b:nib.Nifti1Image.from_bytes(gzip.decompress(b)) )
        self._layerinfo_loader = query.build_lazyloader(
            "layerinfo.txt",folder,
            lambda b:np.array([
                tuple(l.split(' ')[1:])
                for l in b.decode().strip().split('\n')[1:]],
                dtype=[
                    ('layer','U10'),
                    ('area (micron^2)','f'),
                    ('avg. thickness (micron)','f')
                ]) )

    def load_segmentations(self):
        from PIL import Image
        from io import BytesIO
        index = 0
        result = []
        logger.info(f'Loading cell instance segmentation masks for {self}...')
        while True:
            try:
                target = f'segments_cpn_{index:02d}.tif'
                bytestream = self._query.load_file(target,self.folder)
                result.append(np.array(Image.open(BytesIO(bytestream))))
                index+=1
            except RuntimeError:
                break
        return result

    @property
    def info(self):
        return self._info_loader.data
    
    @property 
    def layers(self):
        """
        6x4 array of cortical layer attributes: 
            Number Name Area(micron**2) AvgThickness(micron)
        """
        return self._layerinfo_loader.data

    @property
    def image(self):
        """
        Nifti1Image representation of the original image patch, 
        with an affine matching it to the histological BigBrain space.
        """
        return self._image_loader.data

    @property
    def coordinate(self):
        """
        Coordinate of this image patch in BigBrain histological space in mm.
        """
        A = self.image.affine
        return spaces.BIG_BRAIN,np.dot(A,[0,0,0,1])[:3]

    def __str__(self):
        return f"BigBrain cortical cell distribution in {self.regionspec} (section {self.info['section_id']}, patch {self.info['patch_id']})"


    def plot(self,title=None):
        """
        Create & return a matplotlib figure illustrating the patch, 
        detected cells, and location in BigBrain space.
        """
        if not HAVE_PYPLOT:
            logger.warning('matplotlib.pyplot not available. Plotting disabled.')
            return None
        if not HAVE_PYPLOT:
            logger.warning('nilearn.plotting not available. Plotting disabled.')
            return None

        from ..commons import pyplot,plotting

        patch = self.image.get_fdata()
        space,xyz = self.coordinate
        tpl = space.get_template().fetch()
        X,Y,A,L = [self.cells[:,i] for i in [0,1,2,3]]
        fig = pyplot.figure(figsize=(12,6))
        pyplot.suptitle(str(self))
        ax1 = pyplot.subplot2grid((1, 4), (0, 0))
        ax2 = pyplot.subplot2grid((1, 4), (0, 1), sharex=ax1,sharey=ax1)
        ax3 = pyplot.subplot2grid((1, 4), (0, 2), colspan=2)
        ax1.imshow(patch,cmap='gray'); ax2.axis('off')
        ax2.imshow(patch,cmap='gray'); 
        ax2.scatter(X,Y,s=np.sqrt(A),c=L); ax2.axis('off')
        view = plotting.plot_img(tpl,cut_coords=xyz,cmap='gray',axes=ax3,display_mode='tiled')
        view.add_markers([xyz])
        return fig
   
class RegionalCellDensityExtractor(FeatureQuery):

    _FEATURETYPE = CorticalCellDistribution
    _JUGIT = GitlabQuery("https://jugit.fz-juelich.de",4790,"v1.0a1")
    _SCIEBO = OwncloudQuery("https://fz-juelich.sciebo.de","yDZfhxlXj6YW7KO")

    def __init__(self):
        FeatureQuery.__init__(self)
        logger.warn(f"PREVIEW DATA! {self._FEATURETYPE.__name__} data is only a pre-release snapshot. Contact support@ebrains.eu if you intend to use this data.")

        for cellfile,data in self._JUGIT.find_files("","segments.txt"):
            print("found cellfile",cellfile)
            region_folder = os.path.dirname(cellfile)
            regionspec = " ".join(region_folder.split('_')[1:])
            cells = np.array([
                [float(w) for w in l.strip().split(' ')]
                for l in data.strip().split('\n')[1:]])
            self.register(CorticalCellDistribution(regionspec,cells,self._SCIEBO,region_folder))
