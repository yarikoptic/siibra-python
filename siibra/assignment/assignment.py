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

from typing import Type, Callable, Dict, Iterable, List, TypeVar, Union
from collections import defaultdict
from itertools import product

from .attribute_qualification import qualify as attribute_qualify

from ..commons_new.register_recall import RegisterRecall
from ..commons_new.logger import logger
from ..attributes import AttributeCollection
from ..concepts import QueryParamCollection
from ..attributes.descriptions import ID, Name
from ..exceptions import InvalidAttrCompException, UnregisteredAttrCompException

V = TypeVar("V")

T = Callable[[AttributeCollection], Iterable[AttributeCollection]]

collection_gen: Dict[Type[AttributeCollection], List[V]] = defaultdict(list)

filter_by_query_param = RegisterRecall[List[QueryParamCollection]](cache=False)


def finditer(input: QueryParamCollection, req_type: Type[V]):
    for fn in filter_by_query_param.iter_fn(req_type):
        yield from fn(input)


def find(input: Union[AttributeCollection, QueryParamCollection], req_type: Type[V]) -> List[V]:
    if isinstance(input, AttributeCollection):
        input = QueryParamCollection(criteria=[input])
    return list(finditer(input, req_type))


def string_search(input: str, req_type: Type[V]) -> List[V]:
    id_attr = ID(value=input)
    name_attr = Name(value=input)
    query = AttributeCollection(attributes=[id_attr, name_attr])
    return find(query, req_type)


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
    try:
        if next(qualify(col_a, col_b)):
            return True
        return False
    except StopIteration:
        return False


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
