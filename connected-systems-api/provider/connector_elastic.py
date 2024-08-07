import asyncio
import json
import logging
from typing import Coroutine, Any, Union

from elasticsearch import AsyncElasticsearch
from elasticsearch_dsl import AsyncSearch
from elastic_transport import NodeConfig

from .definitions import *
from pygeoapi.provider.base import ProviderConnectionError, ProviderInvalidDataError, ProviderQueryError, \
    ProviderItemNotFoundError

LOGGER = logging.getLogger(__name__)


def parse_datetime_params(query: AsyncSearch, parameters: DatetimeParam) -> AsyncSearch:
    # Parse dateTime filter
    if parameters.datetime_start() and parameters.datetime_end():
        query = query.filter("range", validTime_parsed={"gte": parameters.datetime_start().isoformat(),
                                                        "lte": parameters.datetime_end().isoformat()})
    if parameters.datetime_start():
        query = query.filter("range", validTime_parsed={"gte": parameters.datetime_start().isoformat()})
    if parameters.datetime_end():
        query = query.filter("range", validTime_parsed={"lte": parameters.datetime_end().isoformat()})
    return query


def parse_csa_params(query: AsyncSearch, parameters: CSAParams) -> AsyncSearch:
    # Parse id filter
    if parameters.id is not None:
        query = query.filter("terms", _id=parameters.id)
    if parameters.q is not None:
        query = query.query("multi_match", query=parameters.q, fields=["name", "description"])
    return query


def parse_spatial_params(query: AsyncSearch,
                         parameters: Union[
                             DeploymentsParams, SystemsParams, SamplingFeaturesParams, CollectionParams]) -> AsyncSearch:
    # Parse bbox filter
    if parameters.bbox is not None:
        br = f"POINT ({parameters.bbox['y1']} {parameters.bbox['x2']})"
        tl = f"POINT ({parameters.bbox['x1']} {parameters.bbox['y2']})"
        query = query.filter("geo_bounding_box", position={"top_left": tl, "bottom_right": br})
    if parameters.geom is not None:
        query = query.filter("geo_shape", position={"relation": "intersects", "shape": parameters.geom})
    return query


def parse_temporal_filters(query: AsyncSearch, parameters: ObservationsParams | DatastreamsParams) -> AsyncSearch:
    # Parse resultTime filter
    if parameters.resulttime_start() and parameters.resulttime_end():
        query = query.filter("range", validTime_parsed={"gte": parameters.resulttime_start().isoformat(),
                                                        "lte": parameters.resulttime_end().isoformat()})
    if parameters.resulttime_start():
        query = query.filter("range", validTime_parsed={"gte": parameters.resulttime_start().isoformat()})
    if parameters.resulttime_end():
        query = query.filter("range", validTime_parsed={"lte": parameters.resulttime_end().isoformat()})

    # Parse phenomenonTime filter
    if parameters.phenomenontime_start() and parameters.phenomenontime_end():
        query = query.filter("range", validTime_parsed={"gte": parameters.phenomenontime_start().isoformat(),
                                                        "lte": parameters.phenomenontime_end().isoformat()})
    if parameters.phenomenontime_start():
        query = query.filter("range", validTime_parsed={"gte": parameters.phenomenontime_start().isoformat()})
    if parameters.phenomenontime_end():
        query = query.filter("range", validTime_parsed={"lte": parameters.phenomenontime_end().isoformat()})

    return query


@dataclass(frozen=True)
class ElasticSearchConfig:
    hostname: str
    port: int
    user: str
    password: str
    dbname: str


async def _delete_cascade(query: AsyncSearch) -> any:
    # DEBUG only
    # print(json.dumps(query.to_dict(), indent=True, default=str))
    return await query.delete()


class ElasticsearchConnector:
    _es: AsyncElasticsearch

    async def connect_elasticsearch(self, config: ElasticSearchConfig) -> None:
        LOGGER.debug(f'Connecting to Elasticsearch at: https://{config.hostname}:{config.port}/{config.dbname}')
        self._es = AsyncElasticsearch(
            [
                NodeConfig(
                    scheme="https",
                    host=config.hostname,
                    port=config.port,
                    verify_certs=False,
                    ca_certs=None,
                    ssl_show_warn=False,
                )
            ],
            http_auth=(config.user, config.password),
            verify_certs=False)
        if not await self._es.ping():
            msg = f'Cannot connect to Elasticsearch'
            LOGGER.critical(msg)
            raise ProviderConnectionError(msg)

        LOGGER.debug('Determining ES version')
        v = await(self._es.info())
        v = v['version']['number'][:3]
        if float(v) < 8:
            msg = 'only ES 8+ supported'
            LOGGER.critical(msg)
            raise ProviderConnectionError(msg)

    async def setup_elasticsearch(self, mappings: List[Tuple[str, Dict]]) -> None:
        try:
            for index in mappings:
                index_name, index_mapping = index

                if not await (self._es.indices.exists(index=index_name)):
                    await self._es.indices.create(
                        index=index_name,
                        mappings=index_mapping
                    )
        except Exception as e:
            LOGGER.exception(e)

        LOGGER.debug("finished initializing AsyncElasticsearch")

    async def _exists(self, query: AsyncSearch) -> bool:
        # DEBUG only
        # print(json.dumps(query.to_dict(), indent=True, default=str))
        return await query.count() > 0

    async def _delete(self, index: str, identifier: str) -> any:
        # DEBUG only
        # print(json.dumps(query.to_dict(), indent=True, default=str))
        return await self._es.delete(index=index, id=identifier)

    async def search(self,
                     query: AsyncSearch,
                     parameters: CSAParams,
                     excludes=None) -> CSAGetResponse:
        # Select appropriate strategy here: For collections >10k elements search_after must be used
        if excludes is None:
            excludes = []
        # DEBUG only
        print(json.dumps(query.to_dict(), indent=True, default=str))

        found = (await query.source(excludes=excludes)[parameters.offset:parameters.limit].execute()).hits

        count = found.total.value
        if count > 0:
            links = []

            if count >= parameters.limit + parameters.offset:
                links.append({
                    "title": "next",
                    "rel": "next",
                    "href": parameters.nextlink()
                })

            return [h._source.to_dict() for h in found.hits], links
        else:

            # check if this query returns 404 or 200 with empty body in case of no return
            if parameters.id:
                raise ProviderItemNotFoundError()
            else:
                return [], []

    async def create_many(self, index: str, items: List[Tuple[str, Dict]]) -> CSACrudResponse:
        routines = [None] * len(items)

        for i, elem in enumerate(items):
            identifier, item = elem
            # add to ES if not already present
            exists = await self._es.exists(index=index, id=identifier)
            if exists.body:
                raise ProviderInvalidDataError(user_msg='record already exists')
            else:
                routines[i] = self._es.index(index=index, id=identifier, document=item)

        # wait for completion
        await asyncio.gather(*routines)

        # TODO: check if we need to validate something here
        return [item[0] for item in items]
