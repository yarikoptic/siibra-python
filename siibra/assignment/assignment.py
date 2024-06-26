from typing import Type, Callable, Dict, Iterable, List, TypeVar
from functools import wraps
from collections import defaultdict
from itertools import product

from .attribute_match import match as attribute_match
from .attribute_qualification import qualify as attribute_qualify

from ..commons import logger
from ..commons_new.iterable import NonUniqueError
from ..concepts import AttributeCollection
from ..concepts.attribute import TruthyAttr
from ..concepts import QueryParam
from ..descriptions import ID, Name
from ..exceptions import InvalidAttrCompException, UnregisteredAttrCompException

V = TypeVar("V")

T = Callable[[AttributeCollection], Iterable[AttributeCollection]]

collection_gen: Dict[Type[AttributeCollection], List[V]] = defaultdict(list)


def register_collection_generator(type_of_col: Type[V]):
    """Register function to be called to yield a specific type of AttributeCollection."""

    def outer(fn: Callable[[AttributeCollection], Iterable[V]]):
        collection_gen[type_of_col].append(fn)

        @wraps(fn)
        def inner(*args, **kwargs):
            return fn(*args, **kwargs)

        return inner

    return outer


def iter_attr_col(reg_type: Type[V]) -> Iterable[V]:
    collection = AttributeCollection(attributes=[TruthyAttr()])
    yield from find(collection, reg_type)


def attr_col_as_dict(reg_type: Type[V]) -> Dict[str, V]:
    return_dict: Dict[str, V] = {}
    for item in iter_attr_col(reg_type):
        try:
            name = item._get(Name)
            return_dict[name.value] = item
        except NonUniqueError:
            logger.warning(f"{item} has non unique name")
            continue
    return return_dict


def finditer(input: AttributeCollection, req_type: Type[V]) -> Iterable[V]:
    for fn in collection_gen[req_type]:
        try:
            yield from fn(input)
        except UnregisteredAttrCompException:
            continue


def find(input: AttributeCollection, req_type: Type[V]) -> List[V]:
    return list(finditer(input, req_type))


def string_search(input: str, req_type: Type[V]) -> Iterable[V]:
    id_attr = ID(value=input)
    name_attr = Name(value=input)
    query = QueryParam(attributes=[id_attr, name_attr])
    yield from find(query, req_type)


def filter_collections(
    filter: AttributeCollection, raw_list: Iterable[V]
) -> Iterable[V]:
    """Given an Iterable of V, raw_list, and a query AttributeCollection, filter, yield instances of V
    which matches with the filter AttributeCollection

    Parameter
    ---------
    filter: AttributeCollection
    raw_list: Iterable[T]

    Returns
    -------
    Iterable[T]
    """
    for item in raw_list:
        try:
            if match(filter, item):
                yield item
        except UnregisteredAttrCompException:
            continue


def match(col_a: AttributeCollection, col_b: AttributeCollection) -> bool:
    """Given AttributeCollection col_a, col_b, compare the product of their respective
    attributes, until:

    - If any of the permutation of the attribute matches, returns True.
    - If InvalidAttrCompException is raised, return False.
    - All product of attributes are exhausted.

    If all product of attributes are exhausted:

    - If any of the comparison called successfully (without raising), return False
    - If none of the comparison called successfully (without raising), raise UnregisteredAttrCompException
    """
    attr_compared_flag = False
    for attra, attrb in product(col_a.attributes, col_b.attributes):
        try:
            match_result = attribute_match(attra, attrb)
            attr_compared_flag = True
            if match_result:
                return True
        except UnregisteredAttrCompException:
            continue
        except InvalidAttrCompException as e:
            logger.debug(f"match exception {e}")
            return False
    if attr_compared_flag:
        return False
    raise UnregisteredAttrCompException


def qualify(col_a: AttributeCollection, col_b: AttributeCollection):
    attr_compared_flag = False
    for attra, attrb in product(col_a.attributes, col_b.attributes):
        try:
            match_result = attribute_qualify(attra, attrb)
            attr_compared_flag = True
            if match_result:
                yield attra, attrb, match_result
        except UnregisteredAttrCompException:
            continue
        except InvalidAttrCompException as e:
            logger.debug(f"match exception {e}")
            return
    if attr_compared_flag:
        return
    raise UnregisteredAttrCompException
