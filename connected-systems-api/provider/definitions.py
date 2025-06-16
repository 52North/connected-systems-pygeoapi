# =================================================================
# Copyright (C) 2024 by 52 North Spatial Information Research GmbH
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# =================================================================
import dataclasses
import logging
import urllib.parse
from dataclasses import dataclass
from datetime import datetime as DateTime
from enum import Enum, auto
from typing import List, Optional, Dict, Tuple, TypeAlias, Text, ClassVar

from elasticsearch_dsl import AsyncDocument, Keyword, AttrDict, DateRange

from provider import es_conn_part1
from provider.util import _format_date_range
from util import MimeType

TimeInterval: TypeAlias = Tuple[Optional[DateTime], Optional[DateTime]]
CSAGetResponse: TypeAlias = Tuple[List[Dict], List[Dict]] | None
CSACrudResponse: TypeAlias = str | List[str]

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(level='INFO')


class EntityType(Enum):
    SYSTEMS = auto()
    DEPLOYMENTS = auto()
    PROCEDURES = auto()
    SAMPLING_FEATURES = auto()
    PROPERTIES = auto()
    DATASTREAMS = auto()
    DATASTREAMS_SCHEMA = auto()
    OBSERVATIONS = auto()


@dataclass
class CSAParams:
    _parameters = ["f", "id", "q", "limit", "offset"]
    _url: str = None
    f: str = "html"  # format
    id: List[str] = None
    q: Optional[List[str]] = None
    limit: int = 10
    offset: int = 0  # non-standard

    @property
    def format(self) -> str:
        return self.f

    @format.setter
    def format(self, inp):
        self.f = inp

    def nextlink(self) -> str:
        values = {k: v for k, v in dataclasses.asdict(self).items() if v is not None and not k.startswith("_")}
        values["offset"] += values["limit"]
        return (self._url
                + "?"
                + urllib.parse.urlencode(values))


@dataclass
class BBoxParam:
    bbox: Optional[Dict] = None


@dataclass
class GeomParam:
    geom: Optional[str] = None


@dataclass
class ResulttimePhenomenontimeParam(CSAParams):
    phenomenonTime: str = None  # unparsed original value
    resultTime: str = None  # unparsed original value

    _phenomenonTime: TimeInterval = None
    _resultTime: TimeInterval = None

    def phenomenontime_start(self):
        return self._phenomenonTime[0] if self._phenomenonTime else None

    def phenomenontime_end(self):
        return self._phenomenonTime[1] if self._phenomenonTime else None

    def resulttime_start(self):
        return self._resultTime[0] if self._resultTime else None

    def resulttime_end(self):
        return self._resultTime[1] if self._resultTime else None


@dataclass
class DatetimeParam(CSAParams):
    datetime: str = None  # unparsed original value
    _datetime: TimeInterval = None

    def datetime_start(self):
        return self._datetime[0] if self._datetime else None

    def datetime_end(self):
        return self._datetime[1] if self._datetime else None


@dataclass
class FoiObservedpropertyParam(CSAParams):
    foi: Optional[List[str]] = None
    observedProperty: Optional[List[str]] = None


@dataclass(slots=True)
class CollectionParams(DatetimeParam, FoiObservedpropertyParam, CSAParams, BBoxParam, GeomParam):
    _parameters = ["f", "id", "q", "datetime", "limit", "offset", "foi", "observedProperty", "bbox", "geom"]
    pass


@dataclass(slots=True)
class SystemsParams(DatetimeParam, FoiObservedpropertyParam, BBoxParam, GeomParam):
    _parameters = ["f", "id", "q", "datetime", "limit", "offset", "bbox", "foi", "observedProperty", "parent", "procedure",
                   "controlledProperty", "geom"]
    parent: Optional[List[str]] = None
    procedure: Optional[List[str]] = None
    controlledProperty: Optional[List[str]] = None


@dataclass(slots=True)
class DeploymentsParams(DatetimeParam, FoiObservedpropertyParam, BBoxParam, GeomParam):
    _parameters = ["f", "id", "q", "datetime", "limit", "offset", "bbox", "foi", "observedProperty", "system", "geom"]
    system: Optional[List[str]] = None


@dataclass(slots=True)
class ProceduresParams(DatetimeParam, FoiObservedpropertyParam):
    _parameters = ["f", "id", "q", "datetime", "limit", "offset", "foi", "observedProperty", "controlledProperty"]
    controlledProperty: Optional[List[str]] = None


@dataclass(slots=True)
class SamplingFeaturesParams(DatetimeParam, FoiObservedpropertyParam, BBoxParam, GeomParam):
    _parameters = ["f", "id", "q", "datetime", "limit", "offset", "bbox", "foi", "observedProperty", "controlledProperty", "system",
                   "geom"]
    controlledProperty: Optional[List[str]] = None
    system: Optional[List[str]] = None


@dataclass(slots=True)
class DatastreamsParams(FoiObservedpropertyParam, ResulttimePhenomenontimeParam):
    _parameters = ["f", "id", "q", "limit", "offset", "foi", "observedProperty", "system", "phenomenonTime",
                   "resultTime"]
    system: Optional[List[str]] = None
    schema: Optional[bool] = None


@dataclass(slots=True)
class ObservationsParams(FoiObservedpropertyParam, ResulttimePhenomenontimeParam):
    _parameters = ["f", "id", "q", "limit", "offset", "foi", "observedProperty", "datastream", "phenomenonTime",
                   "resultTime"]
    datastream: Optional[str] = None


class Collection(AsyncDocument):
    id = Keyword()

    class Index:
        name = "collections"
        using = es_conn_part1


class ConnectedSystemsProvider:
    """Base provider for Providers implementing Parts of Connected Systems API"""

    def __init__(self, provider_def):
        pass

    async def open(self):
        pass

    async def setup(self):
        pass

    async def close(self):
        pass

    def get_conformance(self) -> List[str]:
        """Returns the list of conformance classes that are implemented by this provider"""
        return []

    async def create(self, type: EntityType, encoding: MimeType, item: Dict) -> CSACrudResponse:
        """
        Create a new item

        :param item: `dict` of new item

        :returns: identifier of created item
        """

        raise NotImplementedError()

    async def update(self, type: EntityType, encoding: MimeType, identifier: str, item: Dict):
        """
        Updates an existing item

        :param type: type of collection
        :param identifier: feature id
        :param item: `dict` of partial item

        :returns: `bool` of update result
        """

        raise NotImplementedError()

    async def replace(self, type: EntityType, encoding: MimeType, identifier: str, item: Dict):
        """
        Replaces an existing item

        :param identifier: feature id
        :param item: `dict` of partial or full item

        :returns: `bool` of update result
        """

        raise NotImplementedError()

    async def delete(self, type: EntityType, identifier: str, cascade: bool = False):
        """
        Deletes an existing item

        :param identifier: item id

        :returns: `bool` of deletion result
        """

        raise NotImplementedError()


class ConnectedSystemsPart2Provider(ConnectedSystemsProvider):
    """Base provider for Providers implemented Connected Systems API Part 2"""

    async def query_datastreams(self, parameters: DatastreamsParams) -> CSAGetResponse:
        """
        implements queries on datastreams as specified in openapi-connectedsystems-2

        :returns: dict of formatted properties
        """

        raise NotImplementedError()

    async def query_observations(self, parameters: ObservationsParams) -> CSAGetResponse:
        """
        implements queries on observations as specified in openapi-connectedsystems-2

        :returns: dict of formatted properties
        """

        raise NotImplementedError()


class ConnectedSystemsPart1Provider(ConnectedSystemsProvider):
    """Base provider for Providers implementing Connected Systems API Part 1"""

    async def query_collections(self, parameters: CollectionParams) -> CSAGetResponse:
        """
        implements queries on collections as specified in openapi-connectedsystems-1

        :returns: dict of formatted collections matching the query parameters
        """

        raise NotImplementedError()

    async def query_collection_items(self, collection_id: str, parameters: CSAParams) -> CSAGetResponse:
        """
        implements queries on items in collections as specified in openapi-connectedsystems-1

        :returns: dict of formatted systems matching the query parameters
        """

        raise NotImplementedError()

    async def query_systems(self, parameters: SystemsParams) -> CSAGetResponse:
        """
        implements queries on systems as specified in openapi-connectedsystems-1

        :returns: dict of formatted systems matching the query parameters
        """

        raise NotImplementedError()

    async def query_deployments(self, parameters: DeploymentsParams) -> CSAGetResponse:
        """
        implements queries on deployments as specified in openapi-connectedsystems-1

        :returns: dict of formatted deployments matching the query parameters
        """

        raise NotImplementedError()

    async def query_procedures(self, parameters: ProceduresParams) -> CSAGetResponse:
        """
        implements queries on procedures as specified in openapi-connectedsystems-1

        :returns: dict of formatted procedures matching the query parameters
        """

        raise NotImplementedError()

    async def query_sampling_features(self, parameters: SamplingFeaturesParams) -> CSAGetResponse:
        """
        implements queries on samplingFeatures as specified in openapi-connectedsystems-1

        :returns: dict of formatted samplingFeatures matching the query parameters
        """

        raise NotImplementedError()

    async def query_properties(self, parameters: CSAParams) -> CSAGetResponse:
        """
        implements queries on properties as specified in openapi-connectedsystems-1

        :returns: dict of formatted properties
        """

        raise NotImplementedError()


class CSDocument(AsyncDocument):
    uid = Keyword()
    name: str
    description: Optional[Text]
    validTime: Optional[DateRange] = DateRange()

    mime: ClassVar[MimeType]
    raw: ClassVar[AttrDict]

    async def save(self, **kwargs):
        if self.mime == MimeType.F_GEOJSON.value:
            self.validTime = _format_date_range("validTime", self.raw["properties"])
            self.uid = self.raw["properties"]["uid"]
            self.name = self.raw["properties"]["name"]
            self.description = self.raw["properties"]["description"]
        elif self.mime == MimeType.F_SMLJSON.value:
            self.validTime = _format_date_range("validTime", self.raw)
            self.uid = self.raw.uniqueId
            self.name = getattr(self.raw, "label", None)
            self.description = getattr(self.raw, "description", None)

        delattr(self, "mime")
        delattr(self, "raw")
        await super().save(**kwargs)
