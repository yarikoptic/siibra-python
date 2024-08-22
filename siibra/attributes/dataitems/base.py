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

from dataclasses import dataclass, field
from pathlib import Path
import requests
from typing import Generic, TypeVar, List, Callable

try:
    from typing import TypedDict
except ImportError:
    # support python 3.7
    from typing_extensions import TypedDict

from ...attributes import Attribute
from ...cache import fn_call_cache
from ...retrieval.file_fetcher import (
    ZipRepository,
    TarRepository,
    LocalDirectoryRepository,
)


class Archive(TypedDict):
    file: str = None
    format: str = None


@fn_call_cache
def get_bytesio_from_url(url: str, archive_options: Archive = None) -> bytes:
    if Path(url).is_file():
        pth = Path(url)
        return LocalDirectoryRepository(pth.parent).get(pth.name)
    # TODO: stream bytesio instead
    if not archive_options:
        resp = requests.get(url)
        resp.raise_for_status()
        return resp.content

    if archive_options["format"] == "zip":
        ArchiveRepoType = ZipRepository
    elif archive_options["format"] == "tar":
        ArchiveRepoType = TarRepository
    else:
        raise NotImplementedError(
            f"{archive_options['format']} is not a supported archive format yet."
        )

    filename = archive_options["file"]
    assert filename, "Data attribute 'file' field not populated!"
    repo = ArchiveRepoType(url)
    return repo.get(filename)


src_remote_tar = {
    "type": "src/remotetar",
    "tar": "http://foo/bar.tar",
    "filename": "bazz/bud.txt",
}

src_local_tar = {
    "type": "src/localtar",
    "tar": "/tmp/bar.tar",
    "filename": "bazz/bud.txt",
}

src_remote_file = {"type": "src/file", "url": "http://foo/bud.txt"}

codec_gzip = {
    "type": "codec/gzip",
    "op": "decompress",
}


codec_slice = {"type": "codec/slice", "offset": 200, "bytes": 24}

read_nib = {"type": "read/nibabel"}

read_csv = {"type": "read/csv"}

codec_vol_slice = {
    "type": "codec/vol/slice",
    "param": [],
}

codec_vol_mask = {"type": "codec/vol/mask", "threshold": 0.1}

codec_vol_extract_label = {"type": "codec/vol/extractlabel", "labels": [1, 5, 11]}

codec_vol_to_bytes = {"type": "codec/vol/tobytes"}

dst_return = {"type": "dst/return"}

dst_save_to_file = {"type": "dst/save", "filename": "foo.nii.gz"}

dst_upload = {
    "type": "dst/upload/dataproxy",
    "token": "ey...",
    "bucket": "mybucket",
    "filename": "foobar.nii.gz",
}

"""
rules:

1. all steps *must* accept an input (except src)
2. all steps *must* produce an output (except dst)
3. all steps should do their own input validation

we can also create a text description on a "dry-run". e.g.

1. fetch tar file from http://, extract and get filename
2. gunzip the file
3. read it as nifti with nibabel
4. mask it with threshold 0.3
5. convert the nifti to bytes
6. gzip the result
7. save to my.nii.gz

potentially, we can do things like forking/merging etc (need to be a bit careful about mutability of data)

"""


# example of implementation of a step processor
def process_codec_vol_mask(input, *, cfg, **kwargs):
    import nibabel as nib
    import numpy as np

    threshold = cfg.get("threshold")
    assert isinstance(input, nib.nifti1.Nifti1Image)
    dataobj = input.dataobj
    dataobj = dataobj[dataobj > threshold]
    return nib.nifti1.Nifti1Image(dataobj, affine=input.affine, header=input.header)


def get_runner(*args, **kwargs):
    pass


# TODO should be renamed DataProvider / DataSource?
@dataclass
class Data(Attribute):
    schema: str = "siibra/attr/data"
    key: str = None
    url: str = None
    archive_options: Archive = None

    presteps: List = field(default_factory=list)
    poststeps: List = field(default_factory=list)

    @property
    def steps(self):
        if not self.url:
            return []

        if not self.archive_options:
            return [{"type": "src/file", "url": self.url}]

        if self.archive_options["format"] == "tar":
            return [
                {
                    "type": "src/remotetar",
                    "tar": self.url,
                    "filename": self.archive_options["file"],
                }
            ]
        if self.archive_options["format"] == "zip":
            return [
                {
                    "type": "src/remotezip",
                    "tar": self.url,
                    "filename": self.archive_options["file"],
                }
            ]
        raise NotImplementedError

    def run(self):
        result = None
        for step in [*self.presteps, *self.steps, *self.poststeps]:
            runner = get_runner(step)
            result = runner(result)
        return result

    def get_data(self) -> bytes:
        """
        If the data is provided in an archived format, it is decoded using the
        otherwise bytes are returned without additional steps. This is so that
        the subclasses do not need to implement their own.

        Usage
        -----
        For subclasses, call super().get_data() -> bytes
        """
        return get_bytesio_from_url(self.url, self.archive_options)

    def fetch(self):
        raise NotImplementedError


T = TypeVar("T")


@dataclass
class TransformePipeline(Generic[T]):

    source: Data

    transformers: List[Callable[[T], T]] = field(default_factory=list)

    def transform(self, **kwargs):
        val = self.source.fetch(**kwargs)

    def fetch(self, **kwargs):
        val = super().fetch(**kwargs)
        for transformer in self.transformers:
            val = transformer(val)
        return val
