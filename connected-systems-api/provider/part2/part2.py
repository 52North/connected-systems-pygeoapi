import json
import uuid
from http import HTTPStatus
from pprint import pformat

import asyncpg
import elasticsearch
from asyncpg import Connection
from elasticsearch_dsl import async_connections
from pygeoapi.provider.base import ProviderGenericError, ProviderItemNotFoundError, ProviderInvalidQueryError

from .formats.om_json_scalar import OMJsonSchemaParser
from .util import TimescaleDbConfig, ObservationQuery, Observation
from .. import es_conn_part2
from ..datastream import Datastream
from ..definitions import *
from ..deployment import Deployment
from ..elasticsearch import ElasticsearchConnector, ElasticSearchConfig, parse_csa_params, \
    parse_temporal_filters
from ..system import System

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel('INFO')


class Cache:
    """
    Small cache using circular buffer used for caching whether datastreams exist.
    """
    __cache: [str] = [""] * 128
    __pointer: int = 0

    async def exists(self, identifier: str) -> bool:
        if identifier in self.__cache:
            # Identifier is in cache
            return True
        elif await Datastream.exists(id=identifier):
            # Request and update cache if matching
            self.__cache[self.__pointer] = identifier
            self.__pointer = (self.__pointer + 1) % 128
            return True
        else:
            return False

    def remove(self, identifier: str):
        """removes element with given identifier from the list. Does not change the pointer"""
        for elem in self.__cache:
            if elem == identifier:
                del elem


class ConnectedSystemsTimescaleDBProvider(ConnectedSystemsPart2Provider, ElasticsearchConnector):
    _pool: asyncpg.connection = None
    _cache: Cache = Cache()

    def __init__(self, provider_def):
        super().__init__(provider_def)
        self.base_url = provider_def["base_url"]
        self._ts_config = TimescaleDbConfig(
            hostname=provider_def["timescale"]["host"],
            port=provider_def["timescale"]["port"],
            user=provider_def["timescale"]["user"],
            password=provider_def["timescale"]["password"],
            dbname=provider_def["timescale"]["dbname"],
        )

        self._es_config = ElasticSearchConfig(
            connector_alias=es_conn_part2,
            hostname=provider_def["elastic"]["host"],
            port=provider_def["elastic"]["port"],
            user=provider_def["elastic"]["user"],
            password=provider_def["elastic"]["password"],
            verify_certs=provider_def["elastic"].get("verify_certs", True),
            ca_certs=provider_def["elastic"].get("ca_certs", None),
        )
        self.parser = OMJsonSchemaParser()

    async def open(self):
        LOGGER.info(f"""
                    ====== Connecting to TimescaleDB with configuration ====== 
                        {pformat(self._ts_config)}
                    """)
        self._pool = await asyncpg.create_pool(self._ts_config.connection_string(),
                                               min_size=self._ts_config.pool_min_size,
                                               max_size=self._ts_config.pool_max_size)

        await self.connect_elasticsearch(self._es_config)
        await self.setup()

    async def close(self):
        await self._pool.close()
        es = async_connections.get_connection(es_conn_part2)
        await es.close()

    async def setup(self):
        ## Setup TimescaleDB
        statements = ["""CREATE EXTENSION IF NOT EXISTS POSTGIS;"""]

        if self._ts_config.drop_tables:
            statements.append("""DROP TABLE IF EXISTS observations;""")

        statements.append("""CREATE TABLE IF NOT EXISTS observations (
                                                                uuid UUID DEFAULT gen_random_uuid(),
                                                                resulttime TIMESTAMPTZ NOT NULL,
                                                                phenomenontime TIMESTAMPTZ,
                                                                datastream_id TEXT NOT NULL,
                                                                result BYTEA NOT NULL,
                                                                sampling_feature_id text,
                                                                procedure_link text,
                                                                parameters text
                                                            );
                                                            """)

        statements.append("""SELECT create_hypertable(
                                        'observations',
                                        by_range('resulttime'),
                                        if_not_exists => TRUE
                                    );
                                    """)

        connection: Connection
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                for stmnt in statements:
                    await connection.execute(stmnt)

        await Datastream.init()

    def get_conformance(self) -> List[str]:
        """Returns the list of conformance classes that are implemented by this provider"""
        LOGGER.error("TODO: define conformance classes")
        return []

    async def create(self, type: EntityType, encoding: MimeType, item: Dict) -> CSACrudResponse:
        """
        Create a new item

        :param item: `dict` of new item

        :returns: identifier of created item
        """
        if type == EntityType.DATASTREAMS:
            # check if duplicate identifier
            if "id" not in item:
                # We may have to generate id as it is not always required
                identifier = str(uuid.uuid4())
                item["id"] = identifier
            else:
                if await Datastream().exists(id=item["id"]):
                    raise ProviderItemNotFoundError(user_msg=f"entity with id {item['id']} already exists!")
                else:
                    identifier = item["id"]

            # check if linked system exists
            if not await System().exists(id=item["system"]):
                raise ProviderItemNotFoundError(f"no system with id {item['system']} found!")
            else:
                item["system@link"] = {
                    "href": f"{self.base_url}/systems/{item['system']}"
                }

            # check if linked deployment exists
            deployment = item["deployment@link"]
            if deployment:
                href = deployment["href"]
                if not href.startswith("http://") and not href.startswith("https://"):
                    # Check that locally referenced Deployment exists
                    query = Deployment().search().filter("term", uid=href)
                    found = await query.source(includes=["_id"]).execute()
                    if found:
                        item["deployment@link"] = {
                            "href": f"{self.base_url}/deployments/{found.hits.hits[0]._id}",
                            "urn": href,
                            "title": href
                        }
                    else:
                        raise ProviderItemNotFoundError(f"no deplyoment with urn {href} found!")

            # create in elasticsearch

            try:

                ds = Datastream(raw=item)
                ds.meta.id = identifier

                await ds.save(refresh=True)
                return identifier
            except Exception as e:
                raise ProviderGenericError(f"error saving datastream {e}")

        elif type == EntityType.OBSERVATIONS:
            # check if linked datastream exists
            if not await self._cache.exists(item['datastream']):
                raise ProviderItemNotFoundError(f"no datastream with id {item['datastream']} found!")

            # create in timescaledb
            # TODO: resolve to different parsers based on something?
            return await self._create_observation(self.parser.decode(item))
        else:
            raise ProviderGenericError(f"unrecognized type: {type}")

    async def _create_observation(self, obs: Observation) -> str:
        connection: Connection
        async with self._pool.acquire() as connection:
            # TODO: use prepared statement
            return str(await connection.fetchval(
                "INSERT INTO observations (resulttime, phenomenontime, datastream_id, result, sampling_feature_id, procedure_link, parameters) VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING uuid;",
                obs.resultTime,
                obs.phenomenonTime,
                obs.datastream_id,
                obs.result,
                obs.sampling_feature_id,
                obs.procedure_link,
                obs.parameters
            ))

    async def replace(self, type: EntityType, identifier: str, item: Dict):
        # /req/create-replace-delete/datastream-update-schema
        # /req/create-replace-delete/observation-schema
        LOGGER.debug(f"replacing {type} {identifier}")
        match type:
            case EntityType.DATASTREAMS:
                try:
                    old = await Datastream().get(id=identifier)
                    new = Datastream(**item)
                    new.meta.id = old.meta.id
                    await new.save()
                    return None
                except elasticsearch.NotFoundError as e:
                    raise ProviderItemNotFoundError(user_msg=f"cannot find {type} with id: {identifier}! {e}")

            case EntityType.DATASTREAMS_SCHEMA:
                return await self._replace_schema(identifier, item)

            case EntityType.OBSERVATIONS:
                raise ProviderGenericError(user_msg=f"replace/update of observations not supported yet!")
        return None

    async def update(self, type: EntityType, identifier: str, item: Dict):
        # /req/update/datastream
        # /req/update/datastream-update-schema
        # /req/update/observation
        LOGGER.debug(f"updating {type} {identifier}")
        match type:
            case EntityType.DATASTREAMS:
                try:
                    entity = await Datastream().get(id=identifier)
                    await entity.update(**item)
                    return None
                except elasticsearch.NotFoundError as e:
                    raise ProviderItemNotFoundError(user_msg=f"cannot find {type} with id: {identifier}! {e}")

            case EntityType.DATASTREAMS_SCHEMA:
                return await self._replace_schema(identifier, item)

            case EntityType.OBSERVATIONS:
                raise ProviderGenericError(user_msg=f"replace/update of observations not supported yet!")
        return None

    async def _replace_schema(self, identifier: str, item: Dict):
        # reject if there are associated observations already
        parameters = ObservationsParams()
        parameters.datastream = identifier
        if len(await self._get_observations(parameters)) > 0:
            e = ProviderInvalidQueryError(
                "cannot update/replace schema of datastream which has associated observations")
            e.http_status_code = HTTPStatus.CONFLICT
            raise e
        try:
            entity = await Datastream().get(id=identifier)
            # prevent dsl from merging schema instead of overwriting
            await entity.update(schema=None)
            await entity.update(schema=item)
        except elasticsearch.NotFoundError:
            raise ProviderItemNotFoundError(user_msg=f"cannot find datastream with id: {identifier}!")

    async def delete(self, type: EntityType, identifier: str, cascade: bool = False):
        """
        Deletes an existing item

        :param identifier: item id

        :returns: `bool` of deletion result
        """

        match type:
            case EntityType.DATASTREAMS:
                # /req/create-replace-delete/datastream-delete-cascade
                #
                if cascade:
                    raise NotImplementedError()
                else:
                    # check that no observations exist
                    parameters = ObservationsParams()
                    parameters.datastream = identifier
                    if len(await self._get_observations(parameters)) > 0:
                        e = ProviderInvalidQueryError(
                            "cannot delete system with nested resources and cascade=false. "
                            "ref: /req/create-replace-delete/datastream-delete-cascade")
                        e.http_status_code = HTTPStatus.CONFLICT
                        raise e
                    try:
                        await Datastream().delete(id=identifier)
                        return None
                    except elasticsearch.NotFoundError:
                        raise ProviderItemNotFoundError(f"No datastream with id {identifier} found!")

            case EntityType.OBSERVATIONS:
                return await self._delete_observation(identifier)
        return None

    async def query_datastreams(self, parameters: DatastreamsParams) -> CSAGetResponse:
        """
        implements queries on datastreams as specified in openapi-connectedsystems-2

        :returns: dict of formatted properties
        """

        query = Datastream.search()
        query = parse_csa_params(query, parameters)
        query = parse_temporal_filters(query, parameters)

        if parameters.system is not None:
            query = query.filter("terms", system=parameters.system)

        LOGGER.debug(json.dumps(query.to_dict(), indent=True, default=str))
        if parameters.schema:
            response = await self.search(query, parameters)
            return list(map(lambda x: x["schema"], response[0])), []
        else:
            return await self.search(query, parameters)

    async def query_observations(self, parameters: ObservationsParams) -> CSAGetResponse:
        """
        implements queries on observations as specified in ogcapi-connectedsystems-2

        :returns: dict of formatted properties
        """
        response = await self._get_observations(parameters)
        if len(response) > 0:
            links = []
            if len(response) == int(parameters.limit) or len(response) == 100_000:
                # page is fully filled - we assume a nextpage exists
                url = self.base_url
                if parameters.datastream:
                    url += f"/datastreams/{parameters.datastream}"
                links.append({
                    "title": "next",
                    "rel": "next",
                    "href": parameters.nextlink()
                })
            return [self.parser.encode(row) for row in response], links
        else:
            # check if this query returns 404 or 200 with empty body in case of no return
            if parameters.id:
                return None
            else:
                return [], []

    async def _get_observations(self, parameters: ObservationsParams) -> list:
        q = ObservationQuery()
        q.with_limit(parameters.limit)

        if parameters.id:
            q.with_id(parameters.id)
        if parameters.offset:
            q.with_offset(parameters.offset)
        if parameters._phenomenonTime:
            q.with_time("phenomenontime", parameters._phenomenonTime)
        if parameters._resultTime:
            q.with_time("resulttime", parameters._resultTime)
        if parameters.datastream:
            q.with_datastream(parameters.datastream)

        async with self._pool.acquire() as connection:
            LOGGER.debug("SELECT * FROM observations " + q.to_sql())
            LOGGER.debug(f"{q.parameters}")
            return await connection.fetch("SELECT * FROM observations " + q.to_sql(), *q.parameters)

    async def _delete_observation(self, identifier: str):
        q = ObservationQuery()
        q.with_id([identifier])
        async with self._pool.acquire() as connection:
            LOGGER.debug("DELETE FROM observations " + q.to_sql(False))
            LOGGER.debug(f"{q.parameters}")
            result: str = await connection.execute("DELETE FROM observations " + q.to_sql(False), *q.parameters)
            if not result.endswith("1"):
                raise ProviderItemNotFoundError(f"No observation with id {identifier} found!")
