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
import urllib.parse
from dataclasses import dataclass
from typing import List, Optional, Dict, Tuple, TypeAlias
from datetime import datetime
from collections import OrderedDict

from pygeoapi.api import F_JSONLD, F_JSON
from pygeoapi.provider.base import ProviderInvalidQueryError

TimeInterval: TypeAlias = Tuple[Optional[datetime], Optional[datetime]]
CSAGetResponse: TypeAlias = Tuple[List[Dict], List[Dict]] | None
CSACrudResponse: TypeAlias = List[str]

F_SWE_JSON = 'swejson'
F_OM_JSON = 'omjson'
F_HTML = 'html'
F_GEOJSON = 'geojson'
F_SENSORML_JSON = 'smljson'

FORMAT_TYPES = OrderedDict((
    (F_HTML, 'text/html'),
    (F_GEOJSON, 'application/geo+json'),
    (F_JSONLD, 'application/ld+json'),
    (F_JSON, 'application/json'),
    (F_SENSORML_JSON, 'application/sml+json'),
    (F_SWE_JSON, 'application/swe+json'),
    (F_OM_JSON, 'application/om+json'),
    ('application/sml+json', 'application/sml+json'),
    ('application/swe+json', 'application/swe+json'),
    ('application/om+json', 'application/om+json')
))


@dataclass
class CSAParams:
    _parameters = ["f", "id", "q", "limit", "offset"]
    _url: str = None
    f: str = None  # format
    id: List[str] = None
    q: Optional[List[str]] = None
    limit: int = 10
    offset: int = 0  # non-standard

    @property
    def format(self):
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
    _parameters = ["f", "id", "q", "limit", "offset", "foi", "observedProperty", "bbox", "geom"]
    pass


@dataclass(slots=True)
class SystemsParams(DatetimeParam, FoiObservedpropertyParam, BBoxParam, GeomParam):
    _parameters = ["f", "id", "q", "limit", "offset", "bbox", "foi", "observedProperty", "parent", "procedure",
                   "controlledProperty", "geom"]
    parent: Optional[List[str]] = None
    procedure: Optional[List[str]] = None
    controlledProperty: Optional[List[str]] = None


@dataclass(slots=True)
class DeploymentsParams(DatetimeParam, FoiObservedpropertyParam, BBoxParam, GeomParam):
    _parameters = ["f", "id", "q", "limit", "offset", "bbox", "foi", "observedProperty", "system", "geom"]
    system: Optional[List[str]] = None


@dataclass(slots=True)
class ProceduresParams(DatetimeParam, FoiObservedpropertyParam):
    _parameters = ["f", "id", "q", "limit", "offset", "foi", "observedProperty", "controlledProperty"]
    controlledProperty: Optional[List[str]] = None


@dataclass(slots=True)
class SamplingFeaturesParams(DatetimeParam, FoiObservedpropertyParam, BBoxParam, GeomParam):
    _parameters = ["f", "id", "q", "limit", "offset", "bbox", "foi", "observedProperty", "controlledProperty", "system",
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

    async def create(self, type: str, items: List[Dict]) -> CSACrudResponse:
        """
        Create a new item

        :param item: `dict` of new item

        :returns: identifier of created item
        """

        raise NotImplementedError()

    async def update(self, identifier: str, items: Dict):
        """
        Updates an existing item

        :param identifier: feature id
        :param item: `dict` of partial or full item

        :returns: `bool` of update result
        """

        raise NotImplementedError()

    async def delete(self, identifier: str):
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


def parse_query_parameters(out_parameters: CSAParams, input_parameters: Dict, url: str):
    """
    Parse parameter dict into usable/typed parameters
    """

    def _parse_list(identifier):
        setattr(out_parameters,
                identifier,
                [elem for elem in input_parameters.get(identifier).split(",")])

    def _verbatim(key):
        setattr(out_parameters, key, input_parameters.get(key))

    def _parse_int(key):
        setattr(out_parameters, key, int(input_parameters.get(key)))

    def _parse_time(key):
        val = input_parameters.get(key)
        if "/" in val:
            _parse_time_interval(key)
        else:
            # TODO: check if more edge cases/predefined variables exist
            if val == "now":
                date = datetime.utcnow()
            else:
                date = datetime.fromisoformat(val)
            setattr(out_parameters, key, (date, date))

    def _parse_bbox(key):
        split = input_parameters.get("bbox").split(',')
        if len(split) == 4:
            box = {
                "type": "2d",
                "x1": split[0],  # Lower left corner, coordinate axis 1
                "x2": split[1],  # Lower left corner, coordinate axis 2
                "y1": split[2],  # Upper right corner, coordinate axis 1
                "y2": split[3]  # Upper right corner, coordinate axis 2
            }
        elif len(split) == 6:
            box = {
                "type": "3d",
                "x1": split[0],  # Lower left corner, coordinate axis 1
                "x2": split[1],  # Lower left corner, coordinate axis 2
                "xalt": split[2],  # Minimum value, coordinate axis 3 (optional)
                "y1": split[3],  # Upper right corner, coordinate axis 1
                "y2": split[4],  # Upper right corner, coordinate axis 2
                "yalt": split[5]  # Maximum value, coordinate axis 3 (optional)
            }
        else:
            raise ProviderInvalidQueryError("invalid bbox")
        setattr(out_parameters, "bbox", box)

    def _parse_time_interval(key):
        raw = input_parameters.get(key)
        setattr(out_parameters, key, raw)
        # TODO: Support 'latest' qualifier
        now = datetime.utcnow()
        start, end = None, None
        if "/" in raw:
            # time interval
            split = raw.split("/")
            startts = split[0]
            endts = split[1]
            if startts == "now":
                start = now
            elif startts == "..":
                start = None
            else:
                start = datetime.fromisoformat(startts)
            if endts == "now":
                end = now
            elif endts == "..":
                end = None
            else:
                end = datetime.fromisoformat(endts)
        else:
            if raw == "now":
                start = now
                end = now
            else:
                start = raw
                end = raw
        setattr(out_parameters, "_" + key, (start, end))

    parser = {
        "id": _parse_list,
        "system": _parse_list,
        "parent": _parse_list,
        "q": _verbatim,
        "observedProperty": _parse_list,
        "procedure": _parse_list,
        "controlledProperty": _parse_list,
        "foi": _parse_list,
        "format": _verbatim,
        "f": _verbatim,
        "limit": _parse_int,
        "offset": _parse_int,
        "bbox": _parse_bbox,
        "datetime": _parse_time,
        "geom": _verbatim,
        "datastream": _verbatim,
        "phenomenonTime": _parse_time_interval,
        "resultTime": _parse_time_interval,
    }

    out_parameters._url = url
    #  TODO: There must be a way to make this more efficient/straightforward..
    # Iterate possible parameters
    for p in out_parameters._parameters:
        # Check if parameter is supplied as input
        if p in input_parameters:
            # Parse value with appropriate mapping function
            parser[p](p)

    return out_parameters
