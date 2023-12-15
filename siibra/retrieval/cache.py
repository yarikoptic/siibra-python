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
"""Maintaining and hadnling caching files on disk."""

import hashlib
import os
import pathlib
from appdirs import user_cache_dir
import tempfile
from typing import Union

from ..commons import logger, SIIBRA_CACHEDIR, SKIP_CACHEINIT_MAINTENANCE


def assert_folder(folder: Union[str, pathlib.Path]) -> pathlib.Path:
    # make sure the folder exists and is writable, then return it.
    # If it cannot be written, create and return
    # a temporary folder.
    try:
        path = pathlib.Path(folder) if isinstance(folder, str) else folder
        path.mkdir(parents=True, exist_ok=True)
        if not os.access(path, os.W_OK):
            raise OSError
        return path
    except OSError:
        # cannot write to requested directory, create a temporary one.
        tmpdir = tempfile.mkdtemp(prefix="siibra-cache-")
        logger.warning(
            f"Siibra created a temporary cache directory at {tmpdir}, as "
            f"the requested folder ({folder}) was not usable. "
            "Please consider to set the SIIBRA_CACHEDIR environment variable "
            "to a suitable directory.")
        return pathlib.Path(tmpdir)


class Cache:

    _instance = None
    folder = pathlib.Path(user_cache_dir(".".join(__name__.split(".")[:-1]), ""))
    SIZE_GIB = 2  # maintenance will delete old files to stay below this limit

    def __init__(self):
        raise RuntimeError(
            "Call instance() to access "
            f"{self.__class__.__name__}")

    @classmethod
    def instance(cls):
        """
        Return an instance of the siibra cache. Create folder if needed.
        """
        if cls._instance is None:
            if SIIBRA_CACHEDIR:
                cls.folder = SIIBRA_CACHEDIR
            cls.folder = assert_folder(cls.folder)
            cls._instance = cls.__new__(cls)
            if SKIP_CACHEINIT_MAINTENANCE:
                logger.debug("Will not run maintenance on cache as SKIP_CACHE_MAINTENANCE is set to True.")
            else:
                cls._instance.run_maintenance()
        return cls._instance

    def clear(self):
        import shutil

        logger.info(f"Clearing siibra cache at {self.folder}")
        shutil.rmtree(self.folder)
        self.folder = assert_folder(self.folder)

    def run_maintenance(self):
        """
        Shrinks the cache by deleting oldest files first until the total size
        is below cache size (Cache.SIZE) given in GiB.
        """
        # build sorted list of cache files and their os attributes
        sfiles = sorted([(fn, fn.stat()) for fn in self], key=lambda st: st[1].st_atime)

        current_size = self.size
        for (fn, st) in sfiles:
            if fn.is_dir():
                size = sum(f.stat().st_size for f in fn.rglob('*'))
                import shutil
                shutil.rmtree(fn)
            else:
                size = st.st_size
                fn.unlink()
            current_size -= size / 1024**3
            if current_size <= self.SIZE_GIB:
                break

    @property
    def size(self):
        """Return size of the cache in GiB."""
        return sum(fn.stat().st_size for fn in self.folder.rglob('*')) / 1024**3

    def __iter__(self):
        """Iterate all element names in the cache directory. (Not recursive)"""
        return self.folder.iterdir()

    def build_filename(self, str_rep: str, suffix: str = None):
        """
        Generate a filename in the cache.

        Parameters
        ----------
        str_rep: str
            Unique string representation of the item. Will be used to compute a hash.
        suffix: str. Default: None
            Optional file suffix, in order to allow filetype recognition by the name.

        Returns
        -------
        pathlib.Path
            file path in the cache
        """
        hexrep = str(hashlib.sha256(str_rep.encode("ascii")).hexdigest())
        if suffix:
            suffix = suffix if suffix.startswith(".") else "." + suffix
            return self.folder.joinpath(hexrep).with_suffix(suffix)
        else:
            return self.folder.joinpath(hexrep)


CACHE = Cache.instance()
