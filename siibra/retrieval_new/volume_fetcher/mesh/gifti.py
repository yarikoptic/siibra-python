from typing import TYPE_CHECKING
import gzip

from nibabel.gifti import gifti

from ...volume_fetcher.volume_fetcher import FetchKwargs, register_volume_fetcher

if TYPE_CHECKING:
    from ....dataitems import Mesh


@register_volume_fetcher("gii-mesh", "mesh")
def fetch_gii_mesh(mesh: "Mesh", fetchkwargs: FetchKwargs) -> "gifti.GiftiImage":
    if fetchkwargs["bbox"] is not None:
        raise NotImplementedError
    if fetchkwargs["resolution_mm"] is not None:
        raise NotImplementedError
    if fetchkwargs["color_channel"] is not None:
        raise NotImplementedError

    _bytes = mesh.get_data()
    try:
        return gifti.GiftiImage.from_bytes(gzip.decompress(_bytes))
    except gzip.BadGzipFile:
        return gifti.GiftiImage.from_bytes(_bytes)


@register_volume_fetcher("gii-label", "mesh")
def fetch_gii_label(mesh: "Mesh", fetchkwargs: FetchKwargs) -> "gifti.GiftiImage":
    if fetchkwargs["bbox"] is not None:
        raise NotImplementedError
    if fetchkwargs["resolution_mm"] is not None:
        raise NotImplementedError
    if fetchkwargs["color_channel"] is not None:
        raise NotImplementedError

    _bytes = mesh.get_data()
    try:
        gii = gifti.GiftiImage.from_bytes(gzip.decompress(_bytes))
    except gzip.BadGzipFile:
        gii = gifti.GiftiImage.from_bytes(_bytes)

    return gii