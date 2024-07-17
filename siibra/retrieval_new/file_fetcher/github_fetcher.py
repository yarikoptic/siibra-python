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

from typing import Iterable
from urllib.parse import quote
from pathlib import Path

from .git_fetcher import GitHttpRepository
from .tar_fetcher import TarRepository


class GithubRepository(GitHttpRepository):
    def __init__(self, owner: str, repo: str, reftag: str, eager=False) -> None:
        url = f"https://github.com/{owner}/{repo}.git"
        super().__init__(url, reftag)
        self.owner = owner
        self.repo = repo
        self.reftag = reftag
        self.tar_repo = TarRepository(
            f"{self.github_api_url}/tarball/{self.branch}", gzip=True
        )
        if eager:
            self.warmup()
            filename = next(self.tar_repo.ls())
            self.tar_repo.relative_path = Path(filename).as_posix().split("/")[0]

    @property
    def github_api_url(self):
        return f"https://api.github.com/repos/{self.owner}/{self.repo}"

    @property
    def github_raw_url(self):
        return (
            f"https://raw.githubusercontent.com/{self.owner}/{self.repo}/{self.reftag}"
        )
    
    def ls(self):
        yield from self.search_files()

    def search_files(self, prefix: str = None) -> Iterable[str]:
        if self.is_warm:
            yield from self.tar_repo.search_files(prefix)
            return
        resp = self.sess.get(
            f"{self.github_api_url}/git/trees/{self.reftag}?recursive=1"
        )
        resp.raise_for_status()
        json_response = resp.json()
        return [
            f["path"]
            for f in json_response.get("tree", [])
            if f["type"] == "blob" and f["type"].startswith(prefix or "")
        ]

    @property
    def unpacked_dir(self):
        return self.tar_repo.unpacked_dir

    def warmup(self, *args, **kwargs):
        self.tar_repo.warmup()

    def get(self, filepath: str):
        if self.is_warm:
            return self.tar_repo.get(filepath)
        resp = self.sess.get(f"{self.github_raw_url}/{quote(filepath, safe='')}")
        resp.raise_for_status()
        return resp.content
