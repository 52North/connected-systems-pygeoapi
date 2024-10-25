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
import logging
import uuid
from datetime import datetime as DateTime
from pprint import pprint, pformat
from typing import Callable, Awaitable, Coroutine

import elasticsearch
from elasticsearch_dsl import async_connections
from pygeoapi.provider.base import ProviderGenericError, ProviderItemNotFoundError

from ..elasticsearch import ElasticsearchConnector, ElasticSearchConfig, parse_csa_params, parse_spatial_params, \
    parse_datetime_params
from ..definitions import *

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(level='INFO')


class ConnectedSystemsESProvider(ConnectedSystemsPart1Provider, ElasticsearchConnector):

    def __init__(self, provider_def: Dict):
        super().__init__(provider_def)
        self._es_config = ElasticSearchConfig(
            connector_alias=es_conn_part1,
            hostname=provider_def['host'],
            port=int(provider_def['port']),
            dbname=provider_def['dbname'],
            user=provider_def['user'],
            password=provider_def['password'],
            verify_certs=provider_def.get('verify_certs', True),
            ca_certs=provider_def.get('ca_certs', "")
        )

    def get_conformance(self) -> List[str]:
        # TODO: check which of these we actually support
        return [
            "http://www.opengis.net/spec/ogcapi-common-1/1.0/conf/core",
        ]

    async def open(self):
        await self.connect_elasticsearch(self._es_config)

    async def setup(self):
        await Collection.init()
        await System.init()
        await Deployment.init()
        await Procedure.init()
        await SamplingFeature.init()
        await Property.init()
        await self.__create_mandatory_collections()

    async def close(self):
        es = async_connections.get_connection(es_conn_part1)
        await es.close()

    async def __create_mandatory_collections(self):
        # Create mandatory collections if not exists

        mandatory = [
            {
                "id": "all_systems",
                "type": "collection",
                "title": "All Systems Instances",
                "description": "All systems registered on this server (e.g. platforms, sensors, actuators, processes)",
                "itemType": "feature",
                "featureType": "system",
                "links": [
                    {
                        "rel": "self",
                        "title": "This document (JSON)",
                        "href": "/collections/all_systems",
                        "type": "application/json"
                    },
                    {
                        "rel": "items",
                        "title": "Access the system instances in this collection (HTML)",
                        "href": "/systems",
                        "type": "text/html"
                    },
                    {
                        "rel": "items",
                        "title": "Access the system instances in this collection (JSON)",
                        "href": "/systems?f=application/json",
                        "type": "application/json"
                    }
                ]
            },
            {
                "id": "all_datastreams",
                "type": "collection",
                "title": "All Systems Datastreams",
                "description": "All datastreams produced by systems registered on this server",
                "itemType": "feature",
                "featureType": "datastreams",
                "links": [
                    {
                        "rel": "self",
                        "title": "This document (JSON)",
                        "href": "/collections/all_datastreams",
                        "type": "application/json"
                    },
                    {
                        "rel": "items",
                        "title": "Access the datastreams in this collection (HTML)",
                        "href": "/datastreams",
                        "type": "text/html"
                    },
                    {
                        "rel": "items",
                        "title": "Access the datastreams in this collection (JSON)",
                        "href": "/datastreams?f=application/json",
                        "type": "application/json"
                    }
                ]
            },
            {
                "id": "all_fois",
                "type": "collection",
                "title": "All Features of Interest",
                "description": "All features of interest observed or affected by systems registered on this server",
                "itemType": "feature",
                "featureType": "featureOfInterest",
                "links": [
                    {
                        "rel": "self",
                        "title": "This document (JSON)",
                        "href": "/collections/all_fois",
                        "type": "application/json"
                    },
                    {
                        "rel": "items",
                        "title": "Access the features of interests in this collection (HTML)",
                        "href": "/featuresOfInterest",
                        "type": "text/html"
                    },
                    {
                        "rel": "items",
                        "title": "Access the features of interests in this collection (JSON)",
                        "href": "/featuresOfInterest?f=application/json",
                        "type": "application/json"
                    }
                ]
            },
            {
                "id": "all_procedures",
                "type": "collection",
                "title": "All Procedures and System Datasheets",
                "description": "All procedures (e.g. system datasheets) implemented by systems registered on this server",
                "itemType": "feature",
                "featureType": "procedure",
                "links": [
                    {
                        "rel": "self",
                        "title": "This document (JSON)",
                        "href": "/collections/all_procedures",
                        "type": "application/json"
                    },
                    {
                        "rel": "items",
                        "title": "Access the procedures in this collection (HTML)",
                        "href": "procedures",
                        "type": "text/html"
                    },
                    {
                        "rel": "items",
                        "title": "Access the procedures in this collection (JSON)",
                        "href": "procedures?f=application/json",
                        "type": "application/json"
                    }
                ]
            }
        ]

        for coll in mandatory:
            if not await Collection.exists(id=coll["id"]):
                c = Collection(**coll)
                c.meta.id = coll["id"]
                await c.save()

            LOGGER.info(f"creating mandatory collection {coll['id']}")

    async def query_collections(self, parameters: CollectionParams) -> CSAGetResponse:
        query = Collection.search()

        query = parse_csa_params(query, parameters)
        query = parse_spatial_params(query, parameters)

        return await self.search(query, parameters)

    async def query_collection_items(self, collection_id: str, parameters: CSAParams) -> CSAGetResponse:
        # TODO: implement this for non-mandatory collections
        if collection_id == "all_systems":
            query = System().search()
        elif collection_id == "all_procedures":
            query = Procedure().search()
        elif collection_id == "all_datastreams":
            query = Datastream().search()
        elif collection_id == "all_fois":
            query = SamplingFeature().search()
        else:
            return None

        if parameters.id:
            query = query.filter("terms", _id=parameters.id)

        return await self.search(query, parameters)

    async def query_systems(self, parameters: SystemsParams) -> CSAGetResponse:
        query = System.search()

        query = parse_datetime_params(query, parameters)
        query = parse_csa_params(query, parameters)
        query = parse_spatial_params(query, parameters)

        if parameters.geom is not None:
            query = query.filter("geo_shape", position={"relation": "intersects", "shape": parameters.geom})

        # By default, only top level systems are included (i.e. subsystems are ommitted)
        # unless query parameter 'parent' or 'id' is set
        if parameters.parent is not None:
            query = query.filter("terms", **{"parent": parameters.parent})
        else:
            pass
            # When requested as a collection
            if not parameters.id:
                query = query.exclude("exists", field="parent")

        for key in ["procedure", "foi", "observedProperty", "controlledProperty"]:
            prop = parameters.__getattribute__(key)
            if prop is not None:
                query = query.filter("terms", **{key: prop})

        return await self.search(query, parameters, ["validTime_parsed"])

    async def query_deployments(self, parameters: DeploymentsParams) -> CSAGetResponse:
        query = Deployment.search()

        query = parse_datetime_params(query, parameters)
        query = parse_csa_params(query, parameters)
        query = parse_spatial_params(query, parameters)

        if parameters.system is not None:
            query = query.filter("terms", system_ids=parameters.system)

        return await self.search(query, parameters, ["system_ids"])

    async def query_procedures(self, parameters: ProceduresParams) -> CSAGetResponse:
        query = Procedure.search()

        query = parse_datetime_params(query, parameters)
        query = parse_csa_params(query, parameters)

        if parameters.controlledProperty is not None:
            # TODO: check if this is the correct property
            query = query.filter("terms", controlledProperty=parameters.controlledProperty)

        return await self.search(query, parameters)

    async def query_sampling_features(self, parameters: SamplingFeaturesParams) -> CSAGetResponse:
        query = SamplingFeature.search()

        query = parse_datetime_params(query, parameters)
        query = parse_csa_params(query, parameters)

        if parameters.controlledProperty is not None:
            # TODO: check if this is the correct property
            query = query.filter("terms", controlledProperty=parameters.controlledProperty)

        if parameters.system is not None:
            query = query.filter("terms", system=parameters.system)

        return await self.search(query, parameters)

    async def query_properties(self, parameters: CSAParams) -> CSAGetResponse:
        query = Property.search()
        query = parse_csa_params(query, parameters)

        return await self.search(query, parameters)

    async def create(self, type: EntityType, item: Dict) -> CSACrudResponse:

        async def duplicate_identifier(item: Dict, entity: AsyncDocument) -> None:
            if "id" in item:
                if await entity.exists(id=entity.id):
                    raise ProviderInvalidQueryError(user_msg=f"entity with id {entity.id} already exists!")

        pre_hook: List[Callable[[Dict, AsyncDocument], Awaitable[None]]] = [duplicate_identifier]
        post_hook: List[Callable[[Dict, AsyncDocument], Awaitable[None]]] = []

        # Special Handling for some fields
        match type:
            case EntityType.SYSTEMS:
                # parse date_range fields to es-compatible format
                async def check_parent(_: Dict, entity: AsyncDocument) -> None:
                    self._format_date_range("validTime", entity)
                    parent_id = getattr(entity, "parent", None)
                    if parent_id and not await System().exists(id=parent_id):
                        # check that parent exists,
                        raise ProviderInvalidQueryError(user_msg=f"cannot find parent system with id: {parent_id}")
                    return None

                pre_hook.append(check_parent)
                entity = System(**item)
            case EntityType.DEPLOYMENTS:
                # parse deployedSystems and possibly link if it is local system identified by urn
                async def link_system(_: Dict, entity: AsyncDocument) -> None:
                    entity.system_ids = []
                    for system in getattr(entity, "deployedSystems", []):
                        href: str = system["system"]["href"]
                        if href.startswith("urn"):
                            query = System().search()
                            query = query.filter("term", uniqueId=href)
                            found = await query.source(includes=["_id"]).execute()
                            if len(found.hits) != 1:
                                raise ProviderInvalidQueryError(
                                    user_msg=f"cannot find local system with urn: {href}")
                            else:
                                entity.system_ids.append(found.hits.hits[0]._id)

                post_hook.append(link_system)
                entity = Deployment(**item)
            case EntityType.PROCEDURES:
                entity = Procedure(**item)
            case EntityType.SAMPLING_FEATURES:
                entity = SamplingFeature(**item)
            case EntityType.PROPERTIES:
                entity = Property(**item)
            case _:
                raise ProviderInvalidQueryError(user_msg=f"unrecognized type {type}")

        # We may have to generate id as it is not always required
        identifier = item["id"] if ("id" in item) else str(uuid.uuid4())
        entity.id = identifier
        entity.meta.id = identifier

        try:
            for hook in pre_hook:
                await hook(item, entity)
            entity.meta.id = identifier
            await entity.save()
            for hook in post_hook:
                await hook(item, entity)
            return identifier
        except Exception as e:
            raise ProviderInvalidQueryError(user_msg=str(e))

    async def replace(self, type: EntityType, identifier: str, item: Dict):
        LOGGER.debug(f"replacing {type} {identifier}")
        old = await self._get_entity(type, identifier)
        new = System(**item)
        new.meta.id = old.meta.id
        await new.save()

    async def update(self, type: EntityType, identifier: str, item: Dict):
        LOGGER.debug(f"updating {type} {identifier}")
        await (await self._get_entity(type, identifier)).update(**item)

    async def delete(self, type: EntityType, identifier: str, cascade: bool = False):
        LOGGER.debug(f"deleting {type} {identifier}")
        try:
            match type:
                case EntityType.SYSTEMS:
                    if not cascade:
                        # /req/create-replace-delete/system
                        # reject if there are nested resources: subsystems, sampling features, datastreams, control streams
                        error_msg = f"cannot delete system with nested resources and cascade=false. "
                        f"ref: /req/create-replace-delete/system"

                        # TODO: Should we run all these checks in parallel or is it more efficient to sync + exit early?
                        # check subsystems
                        if await self._exists(System.search().filter("term", parent=identifier)):
                            raise ProviderInvalidQueryError(user_msg=error_msg)

                        # check deployments
                        if await self._exists(Deployment.search().filter("term", system=identifier)):
                            raise ProviderInvalidQueryError(user_msg=error_msg)

                        # check sampling features
                        if await self._exists(
                                SamplingFeature.search().filter("term", system=identifier)):
                            raise ProviderInvalidQueryError(user_msg=error_msg)

                        entity = await System.get(identifier)
                        # if self._provider_part2:

                    else:
                        # blocked-by: https://github.com/opengeospatial/ogcapi-connected-systems/issues/61
                        # /req/create-replace-delete/system-delete-cascade
                        # async with asyncio.TaskGroup() as tg:
                        #     # recursively delete subsystems with all their associated entities
                        #     subsystems = (AsyncSearch(using=self._es)
                        #                   .index(self.systems_index_name)
                        #                   .filter("term", parent=identifier)
                        #                   .source(False)
                        #                   .scan())
                        #     #async for subsystem in subsystems:
                        #     #    tg.create_task(self.delete("system", subsystem.meta.id, True))
                        #     print((AsyncSearch(using=self._es)
                        #      .index(self.deployments_index_name)
                        #      .filter("term", system=identifier)
                        #      .source(False)).to_dict())
                        #     deployments = (AsyncSearch(using=self._es)
                        #                    .index(self.deployments_index_name)
                        #                    .filter("term", system=identifier)
                        #                    .source(False)
                        #                    .scan())
                        #     async for d in deployments:
                        #         print("deleting deployment?")
                        #         tg.create_task(self.delete("deployment", d.meta.id, True))
                        #
                        #     samplingfeatures = (AsyncSearch(using=self._es)
                        #                         .index(self.samplingfeatures_index_name)
                        #                         .filter("term", system=identifier)
                        #                         .source(False)
                        #                         .scan())
                        #     async for s in samplingfeatures:
                        #         tg.create_task(self.delete("samplingFeature", s.meta.id, True))
                        #
                        # # await self._delete(self.systems_index_name, identifier)
                        return ProviderGenericError("cascade=true is not implemented yet!")
                    entity = await System.get(id=identifier)
                case EntityType.DEPLOYMENTS:
                    entity = await Deployment.get(id=identifier)
                case EntityType.PROCEDURES:
                    entity = await Procedure.get(id=identifier)
                case EntityType.SAMPLING_FEATURES:
                    entity = await SamplingFeature.get(id=identifier)
                case EntityType.PROPERTIES:
                    entity = await Property.get(id=identifier)
                case _:
                    raise ProviderInvalidQueryError(user_msg=f"unrecognized type {type}")
            return await entity.delete()
        except elasticsearch.NotFoundError as e:
            raise ProviderItemNotFoundError(user_msg=f"cannot find {type} with id: {identifier}! {e}")
        except Exception as e:
            raise ProviderGenericError(user_msg=f"error while deleting: {e}")

    async def _get_entity(self, type: EntityType, identifier: str):
        try:
            match type:
                case EntityType.SYSTEMS:
                    entity = System.get(id=identifier)
                case EntityType.DEPLOYMENTS:
                    entity = Deployment.get(id=identifier)
                case EntityType.PROCEDURES:
                    entity = Procedure.get(id=identifier)
                case EntityType.SAMPLING_FEATURES:
                    entity = SamplingFeature.get(id=identifier)
                case EntityType.PROPERTIES:
                    entity = Property.get(id=identifier)
                case _:
                    raise ProviderInvalidQueryError(user_msg=f"unrecognized type {type}")
            return await entity
        except Exception as e:
            raise ProviderItemNotFoundError(user_msg=f"cannot find {type} with id: {identifier}! {e}")

    def _format_date_range(self, key: str, item: AsyncDocument) -> None:
        if hasattr(item, key):
            time = getattr(item, key)
            now = DateTime.now()
            if time[0] == "now":
                start = now
            else:
                start = time[0]
            if time[1] == "now":
                end = now
            else:
                end = time[1]

            item[key + "_parsed"] = {
                "gte": start,
                "lte": end
            }
