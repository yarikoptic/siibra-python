# generated by datamodel-codegen:
#   filename:  sxplr.on.allRegions__fromSxplr__request.json
#   timestamp: 2023-12-07T15:40:35+00:00

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional, Union


@dataclass
class VocabModel:
    field_vocab: str


@dataclass
class QuantitativeOverlapItem:
    value: float
    field_context: Optional[VocabModel] = field(
        default_factory=lambda: {'@vocab': 'https://openminds.ebrains.eu/vocab/'}
    )
    typeOfUncertainty: Optional[Any] = None
    uncertainty: Optional[List[float]] = None
    unit: Optional[Any] = None


@dataclass
class QuantitativeOverlapItem1:
    maxValue: float
    minValue: float
    field_context: Optional[VocabModel] = field(
        default_factory=lambda: {'@vocab': 'https://openminds.ebrains.eu/vocab/'}
    )
    maxValueUnit: Optional[Any] = None
    minValueUnit: Optional[Any] = None


@dataclass
class ApiModelsOpenmindsSANDSV3AtlasParcellationEntityVersionCoordinates:
    value: float
    field_context: Optional[VocabModel] = field(
        default_factory=lambda: {'@vocab': 'https://openminds.ebrains.eu/vocab/'}
    )
    typeOfUncertainty: Optional[Any] = None
    uncertainty: Optional[List[float]] = None
    unit: Optional[Any] = None


@dataclass
class RelationAssessmentItem:
    inRelationTo: Any
    qualitativeOverlap: Any
    field_context: Optional[VocabModel] = field(
        default_factory=lambda: {'@vocab': 'https://openminds.ebrains.eu/vocab/'}
    )
    criteria: Optional[Any] = None


@dataclass
class RelationAssessmentItem1:
    inRelationTo: Any
    quantitativeOverlap: Union[QuantitativeOverlapItem, QuantitativeOverlapItem1]
    field_context: Optional[VocabModel] = field(
        default_factory=lambda: {'@vocab': 'https://openminds.ebrains.eu/vocab/'}
    )
    criteria: Optional[Any] = None


@dataclass
class BestViewPoint:
    coordinateSpace: Any
    coordinates: List[
        ApiModelsOpenmindsSANDSV3AtlasParcellationEntityVersionCoordinates
    ]
    field_context: Optional[VocabModel] = field(
        default_factory=lambda: {'@vocab': 'https://openminds.ebrains.eu/vocab/'}
    )


@dataclass
class HasAnnotation:
    criteriaQualityType: Any
    internalIdentifier: str
    field_context: Optional[VocabModel] = field(
        default_factory=lambda: {'@vocab': 'https://openminds.ebrains.eu/vocab/'}
    )
    bestViewPoint: Optional[BestViewPoint] = None
    criteria: Optional[Any] = None
    displayColor: Optional[str] = None
    inspiredBy: Optional[List] = None
    laterality: Optional[List] = None
    visualizedIn: Optional[Any] = None


@dataclass
class PTRegion:
    field_type: str
    field_id: str
    versionIdentifier: str
    field_context: Optional[VocabModel] = field(
        default_factory=lambda: {'@vocab': 'https://openminds.ebrains.eu/vocab/'}
    )
    hasAnnotation: Optional[HasAnnotation] = None
    hasParent: Optional[List] = None
    lookupLabel: Optional[str] = None
    name: Optional[str] = None
    ontologyIdentifier: Optional[List[str]] = None
    relationAssessment: Optional[
        Union[RelationAssessmentItem, RelationAssessmentItem1]
    ] = None
    versionInnovation: Optional[str] = None


@dataclass
class Model:
    jsonrpc: str = '2.0'
    method: str = 'sxplr.on.allRegions'
    params: Optional[List[PTRegion]] = None
