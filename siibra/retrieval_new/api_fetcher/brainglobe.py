import json
from typing import TypedDict, List, Dict, TYPE_CHECKING
import numpy as np
import nibabel as nib
from PIL import Image as PILImage
from io import BytesIO
from hashlib import md5
from pathlib import Path
from dataclasses import replace

from ...factory.iterator import attribute_collection_iterator
from ...retrieval_new.file_fetcher import GitHttpRepository, TarRepository
from ...concepts import Attribute, AttributeCollection
from ...descriptions import Name, RGBColor, Url, SpeciesSpec, ID
from ...dataitems import Image
from ...commons import logger
from ...commons_new.string import to_hex

if TYPE_CHECKING:
    from ...atlases import Parcellation

url = "https://gin.g-node.org/BrainGlobe/atlases.git"
fileurl = "https://gin.g-node.org/BrainGlobe/atlases/raw/master/{filename}.tar.gz"

repo: GitHttpRepository = None


DESC_INFO = """
------------------------------------
DESC INFO ABOUT USING BRAINGLOBE API
------------------------------------
"""


class Structure(TypedDict):
    structure: str
    id: int
    name: str
    structure_id_path: List[int]
    rgb_triplet: List[int]


class Metadata(TypedDict):
    name: str
    citation: str
    atlas_link: str
    species: str
    symmetric: bool
    resolution: List[float]
    orientation: str
    version: str
    shape: List[int]
    transform_to_bg: List[List[float]]
    additional_references: List


def _get_repo():
    global repo
    if repo is None:
        print(DESC_INFO)
        repo = GitHttpRepository(url=url, branch="master")
    return repo


_registered_atlas = set()


def ls():
    repo = _get_repo()
    return [
        obj.filename.replace(".tar.gz", "")
        for obj in repo.ls()
        if obj.filename.endswith(".tar.gz")
    ]


def populate_regions(
    structures: List[Structure],
    parcellation: "Parcellation",
    additional_attrs: List[Attribute] = None,
):
    from ...atlases import Region as Region

    _dict_id_to_region: Dict[int, Region] = {}
    _dict_region_to_parent: Dict[Region, int] = {}
    regions: List[Region] = []

    # TODO we needed to go through twice because we cannot guarantee that
    # parents appear before children in the list.

    for structure in structures:
        name = Name(value=structure["name"])
        rgb_str = "".join(
            [hex(value)[:2].rjust(2, "0") for value in structure["rgb_triplet"]]
        )
        rgb = RGBColor(value=f"#{rgb_str}")
        _id = ID(value=f"bg-{structure['name']}")

        region = Region(
            attributes=[_id, name, rgb, *(additional_attrs or [])], children=[]
        )
        _dict_id_to_region[structure["id"]] = region

        try:
            _dict_region_to_parent[region] = structure["structure_id_path"][-2]
        except IndexError:
            region.parent = parcellation

        regions.append(region)

    for region in regions:
        if region not in _dict_region_to_parent:
            continue
        parent_id = _dict_region_to_parent[region]
        assert parent_id in _dict_id_to_region, f"{parent_id} not found!"
        parent_region = _dict_id_to_region[parent_id]
        region.parent = parent_region


def tiff_to_nii(tiff_bytes: bytes, affine: np.ndarray) -> str:
    from ...cache import CACHE

    filename = CACHE.build_filename(md5(tiff_bytes).hexdigest(), ".nii")
    if Path(filename).exists():
        return filename

    tiff_img = PILImage.open(BytesIO(tiff_bytes))

    stack = []
    for i in range(tiff_img.n_frames):
        tiff_img.seek(i)
        stack.append(np.array(tiff_img))
    stacked_array = np.stack(stack, axis=-1)
    nii = nib.Nifti1Image(stacked_array, affine)
    nib.save(nii, filename)
    return filename


def use(atlas_name: str):
    from ...atlases import Parcellation, Space, Map

    if atlas_name in _registered_atlas:
        logger.info(f"{atlas_name} is already loaded.")
        return

    space_id = f"bg-{atlas_name}"
    parcellation_id = f"bg-{atlas_name}"

    repo = TarRepository(fileurl.format(filename=atlas_name), gzip=True)

    metadata: Metadata = json.loads(repo.get(f"{atlas_name}/metadata.json"))
    structures: List[Structure] = json.loads(repo.get(f"{atlas_name}/structures.json"))

    speciesspec = SpeciesSpec(value=metadata["species"])
    parcellation = Parcellation(
        attributes=[
            ID(value=parcellation_id),
            Name(value=metadata["name"] + " bg parcellation"),
            Url(value=metadata["atlas_link"]),
            speciesspec,
        ],
        children=[],
    )

    # "trasform_to_bg" typo seen in allen human 500um
    affine = np.array(metadata.get("transform_to_bg") or metadata.get("trasform_to_bg"))
    ref_img_filename = tiff_to_nii(repo.get(f"{atlas_name}/reference.tiff"), affine)
    annot_img_filename = tiff_to_nii(repo.get(f"{atlas_name}/annotation.tiff"), affine)

    populate_regions(structures, parcellation, [speciesspec])

    @attribute_collection_iterator.register(Parcellation)
    def bg_parcellation():
        return [parcellation]

    space = Space(
        attributes=[
            ID(value=space_id),
            Name(value=metadata["name"] + " bg space"),
            Url(value=metadata["atlas_link"]),
            speciesspec,
            Image(format="nii", url=ref_img_filename, space_id=space_id),
        ]
    )

    @attribute_collection_iterator.register(Space)
    def bg_space():
        return [space]

    _region_attributes={
        structure["name"]: {
            "label": structure["id"]
        }
        # AttributeCollection(
        #     attributes=(
        #         replace(
        #             labelled_map_image,
        #             color=to_hex(structure["rgb_triplet"]),
        #             volume_selection_options={"label": structure["id"]},
        #         ),
        #     )
        # )
        for structure in structures
    }
    labelled_map_image = Image(format="nii",
                               url=annot_img_filename,
                               space_id=space_id,
                               mapping=_region_attributes)

    labelled_map = Map(
        parcellation_id=parcellation_id,
        space_id=space_id,
        maptype="labelled",
        attributes=(
            ID(value=f"bg-{space_id}{parcellation_id}"),
            Name(value=f"bg labelled-map {space_id} {parcellation_id}"),
            labelled_map_image,
            speciesspec,
        ),
    )

    @attribute_collection_iterator.register(Map)
    def bg_map():
        return [labelled_map]

    _registered_atlas.add(atlas_name)
    logger.info(f"{atlas_name} added to siibra.")

    return space, parcellation, labelled_map