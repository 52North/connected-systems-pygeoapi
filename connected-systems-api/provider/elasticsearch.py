import json
from dataclasses import field
from pprint import pformat
from typing import Union

from elastic_transport import NodeConfig
from elasticsearch_dsl import AsyncSearch, Q
from elasticsearch_dsl.async_connections import connections
from elasticsearch_dsl.query import Bool
from pygeoapi.provider.base import ProviderConnectionError, ProviderItemNotFoundError

from .definitions import *

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel('INFO')


def parse_datetime_params(query: AsyncSearch, parameters: DatetimeParam) -> AsyncSearch:
    # Parse dateTime filter
    if parameters.datetime_start() and parameters.datetime_end():
        validTime = {"gte": parameters.datetime_start().isoformat(), "lte": parameters.datetime_end().isoformat()}
    elif parameters.datetime_start():
        validTime = {"gte": parameters.datetime_start().isoformat()}
    elif parameters.datetime_end():
        validTime = {"lte": parameters.datetime_end().isoformat()}
    else:
        return query

    return query.query(Bool(filter=[Q("range", validTime=validTime) | ~Q("exists", field="validTime")]))


def parse_csa_params(query: AsyncSearch, parameters: CSAParams) -> AsyncSearch:
    # Parse id filter
    if parameters.id is not None:
        query = query.filter("terms", _id=parameters.id)
    if parameters.q is not None and parameters.q is not "":
        query = query.query("combined_fields", query=parameters.q, fields=["name", "description"])
    return query


def parse_spatial_params(query: AsyncSearch,
                         parameters: Union[
                             DeploymentsParams, SystemsParams, SamplingFeaturesParams, CollectionParams]) -> AsyncSearch:
    # Parse bbox filter
    if parameters.bbox is not None:
        br = f"POINT ({parameters.bbox['y1']} {parameters.bbox['x2']})"
        tl = f"POINT ({parameters.bbox['x1']} {parameters.bbox['y2']})"
        query = query.filter("geo_bounding_box", geometry={"top_left": tl, "bottom_right": br})
    if parameters.geom is not None:
        query = query.filter("geo_shape", geometry={"relation": "intersects", "shape": parameters.geom})
    return query


def parse_temporal_filters(query: AsyncSearch, parameters: ObservationsParams | DatastreamsParams) -> AsyncSearch:
    # Parse resultTime filter
    if parameters.resulttime_start() and parameters.resulttime_end():
        query = query.filter("range", validTime={"gte": parameters.resulttime_start().isoformat(),
                                                 "lte": parameters.resulttime_end().isoformat()})
    if parameters.resulttime_start():
        query = query.filter("range", validTime={"gte": parameters.resulttime_start().isoformat()})
    if parameters.resulttime_end():
        query = query.filter("range", validTime={"lte": parameters.resulttime_end().isoformat()})

    # Parse phenomenonTime filter
    if parameters.phenomenontime_start() and parameters.phenomenontime_end():
        query = query.filter("range", validTime={"gte": parameters.phenomenontime_start().isoformat(),
                                                 "lte": parameters.phenomenontime_end().isoformat()})
    if parameters.phenomenontime_start():
        query = query.filter("range", validTime={"gte": parameters.phenomenontime_start().isoformat()})
    if parameters.phenomenontime_end():
        query = query.filter("range", validTime={"lte": parameters.phenomenontime_end().isoformat()})

    return query


@dataclass(frozen=True)
class ElasticSearchConfig:
    hostname: str
    port: int
    user: str
    verify_certs: bool
    ca_certs: Optional[str]
    connector_alias: str
    password: str = field(repr=False)
    password_censored: str = "***********"


class ElasticsearchConnector:

    async def connect_elasticsearch(self, config: ElasticSearchConfig) -> None:
        LOGGER.info(f"""
            ====== Connecting to ES with configuration ====== 
                {pformat(config)}
            """)

        LOGGER.debug(f'Connecting to Elasticsearch at: https://{config.hostname}:{config.port}')
        try:
            connections.create_connection(
                alias=config.connector_alias,
                hosts=[NodeConfig(
                    scheme="https",
                    host=config.hostname,
                    port=config.port,
                    verify_certs=config.verify_certs,
                    ca_certs=config.ca_certs if config.verify_certs else None,
                    ssl_show_warn=True,
                )],
                timeout=20,
                http_auth=(config.user, config.password),
                verify_certs=config.verify_certs)
        except Exception as e:
            msg = f'Cannot connect to Elasticsearch: {e}'
            LOGGER.critical(msg)
            raise ProviderConnectionError(msg)

    async def _exists(self, query: AsyncSearch) -> bool:
        LOGGER.error(json.dumps(query.to_dict(), indent=True, default=str))
        LOGGER.error(await query.count())
        return (await query.count()) > 0

    async def search(self,
                     query: AsyncSearch,
                     parameters: CSAParams) -> CSAGetResponse:
        # Select appropriate strategy here: For collections >10k elements search_after must be used
        LOGGER.error(json.dumps(query.to_dict(), indent=True, default=str))

        match parameters.format:
            case MimeType.F_SMLJSON.value:
                f = "sml"
            case MimeType.F_GEOJSON.value:
                f = "geojson"
            case MimeType.F_JSON.value:
                f = "json"
            case _:
                raise Exception(f"unrecognized Format {parameters.format}")

        found = (await query.source(f)[parameters.offset:parameters.offset + parameters.limit].execute()).hits

        count = found.total.value
        if count > 0:
            links = []
            if count >= parameters.limit + parameters.offset:
                links.append({
                    "title": "next",
                    "rel": "next",
                    "href": parameters.nextlink()
                })

            LOGGER.error("Add alternative encodings as links here!")

            try:
                return [getattr(x._source, f).to_dict() for x in found.hits], links
            except Exception as e:
                LOGGER.error(e)
                return [], []
        else:

            # check if this query returns 404 or 200 with empty body in case of no return
            if parameters.id:
                raise ProviderItemNotFoundError()
            else:
                return [], []
