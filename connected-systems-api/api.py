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
import os
import pathlib
from http import HTTPMethod

import jsonschema
import orjson
from jsonschema.exceptions import ValidationError
from jsonschema.protocols import Validator
from jsonschema.validators import Draft202012Validator
from pygeoapi.api import *
from pygeoapi.config import get_config
from pygeoapi.openapi import load_openapi_document
from pygeoapi.provider.base import ProviderItemNotFoundError, ProviderInvalidQueryError
from pygeoapi.util import render_j2_template

from meta import CSMeta
from provider.definitions import *
from provider.util import parse_query_parameters
from util import *

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel('DEBUG')


class SchemaValidator:
    system_sml_validator: Validator
    system_geojson_validator: Validator
    deployment_sml_validator: Validator
    deployment_geojson_validator: Validator
    procedure_sml_validator: Validator
    procedure_geojson_validator: Validator
    feature_validator: Validator
    property_validator: Validator
    datastream_validator: Validator
    observation_validator: Validator

    def __init__(self):
        package_dir = pathlib.Path(__file__).parent
        for prop, loc in [("system_sml_validator", "schemas/system.sml.schema"),
                          ("system_geojson_validator", "schemas/system.geojson.schema"),
                          ("procedure_sml_validator", "schemas/procedure.sml.schema"),
                          ("procedure_geojson_validator", "schemas/procedure.geojson.schema"),
                          ("property_validator", "schemas/property.schema"),
                          ("feature_validator", "schemas/samplingFeature.schema"),
                          ("deployment_sml_validator", "schemas/deployment.sml.schema"),
                          ("deployment_geojson_validator", "schemas/deployment.geojson.schema"),
                          ("datastream_validator", "schemas/datastream.schema"),
                          ("observation_validator", "schemas/observation.schema")]:
            with open(os.path.join(package_dir, loc), 'r') as definition:
                setattr(self, prop, Draft202012Validator(json.load(definition)))

    def validate(self, collection: EntityType, encoding: str, instance: any) -> None:
        validator: Validator = None
        match (collection, encoding):
            case (EntityType.SYSTEMS, MimeType.F_SMLJSON.value):
                validator = self.system_sml_validator
            case (EntityType.SYSTEMS, MimeType.F_GEOJSON.value):
                validator = self.system_geojson_validator
            case (EntityType.DEPLOYMENTS, MimeType.F_SMLJSON.value):
                validator = self.deployment_sml_validator
            case (EntityType.DEPLOYMENTS, MimeType.F_GEOJSON.value):
                validator = self.deployment_geojson_validator
            case (EntityType.PROCEDURES, MimeType.F_SMLJSON.value):
                validator = self.procedure_sml_validator
            case (EntityType.PROCEDURES, MimeType.F_GEOJSON.value):
                validator = self.procedure_geojson_validator
            case (EntityType.SAMPLING_FEATURES, MimeType.F_GEOJSON.value):
                validator = self.feature_validator
            case (EntityType.PROPERTIES, MimeType.F_SMLJSON.value):
                validator = self.property_validator
            case (EntityType.DATASTREAMS, MimeType.F_JSON.value):
                validator = self.datastream_validator
            case (EntityType.OBSERVATIONS, MimeType.F_JSON.value):
                validator = self.observation_validator
            case _:
                raise ValidationError(f"invalid encoding '{encoding}' for EntityType: '{collection.name}'. Please specify an encoding!")

        return validator.validate(instance)


class CSAPI(CSMeta):
    """
        API Object implementing OGC API Connected Systems
    """
    validator = SchemaValidator()
    strict_validation1 = True
    strict_validation2 = True

    def __init__(self, config: Dict, openapi: Dict):
        config_prefix = os.getenv("CONFIG_PREFIX", "CSA_")
        # Allow for configuration using environment variables that overwrite values from the provided config
        for key, val in os.environ.items():
            if key.startswith(config_prefix):
                # resolve key to config property
                # config properties may include underscored encoded as __
                path = []
                for e in key.replace("__", "||").split("_"):
                    path.append(e.replace("||", "_"))
                node = config
                for subpath in path[1:-1]:
                    subpath = subpath.lower()
                    if subpath.lower() in node:
                        # descend
                        node = node.get(subpath)
                    else:
                        # key does not exist in the config yet. create it
                        node[subpath] = {}

                LOGGER.debug(f"Overwriting property with env value: {path} --> {val}")
                node[path[-1].lower()] = val

        super().__init__(config, openapi)

        if config['dynamic-resources'] is not None:
            api_part1 = None
            for resource in config['dynamic-resources']:
                if config['dynamic-resources'][resource].get('type') == "connected-systems-part1":
                    api_part1 = config['dynamic-resources'][resource]
            if api_part1 is not None:
                provider_definition = api_part1['provider']
                provider_definition["base_url"] = self.base_url
                self.provider_part1 = load_plugin('provider', provider_definition)

                if api_part1.get("strict_validation", None) is not None:
                    self.strict_validation1 = bool(api_part1["strict_validation"])

                if self.config.get('resources') is None:
                    self.config['resources'] = {}

            api_part2 = None
            for resource in config['dynamic-resources']:
                if config['dynamic-resources'][resource].get('type') == "connected-systems-part2":
                    api_part2 = config['dynamic-resources'][resource]
            if api_part2 is not None:
                provider_definition = api_part2['provider']
                provider_definition["base_url"] = self.base_url
                self.provider_part2 = load_plugin('provider', provider_definition)

                if api_part2.get("strict_validation", None) is not None:
                    self.strict_validation1 = bool(api_part2["strict_validation"])

                if self.config.get('resources') is None:
                    self.config['resources'] = {}

    @parse_request
    @jsonldify
    async def get_collections(self,
                              request: AsyncAPIRequest,
                              template: Tuple[dict, int, str],
                              original_format: str,
                              collection_id: str = None) -> APIResponse:
        """
        Adds Connected-Systems collections to existing response
        """
        # Start new response object if resources is empty, else reuse existing object
        fcm = None
        if template[1] == HTTPStatus.NOT_FOUND:
            fcm = {"collections": [], "links": []}
        else:
            fcm = orjson.loads(template[2])

        # query collections
        data = None
        try:
            if collection_id is not None:
                request.params['id'] = collection_id

            parameters = parse_query_parameters(CollectionParams(), request.params,
                                                self.base_url + "/" + request.path_info)
            parameters.format = original_format
            data = await self.provider_part1.query_collections(parameters)
        except ProviderItemNotFoundError:
            # element was not found in resources nor dynamic-resources, return 404
            if template[1] == HTTPStatus.NOT_FOUND:
                return template
            # else: there is already content

        headers = template[0]
        if data:
            if collection_id is not None:
                headers["Content-Type"] = "application/json"
                return headers, HTTPStatus.OK, orjson.dumps(data[0][0])
            else:
                fcm['collections'].extend(data[0])
                if original_format == F_HTML:  # render
                    fcm['collections_path'] = f"{self.base_url}/collections"
                    headers["Content-Type"] = "text/html"
                    content = render_j2_template(self.tpl_config,
                                                 'collections/index.html',
                                                 fcm,
                                                 request.locale)
                    return headers, HTTPStatus.OK, content
                else:
                    headers["Content-Type"] = "application/json"
                    return headers, HTTPStatus.OK, orjson.dumps(fcm)

        return headers, HTTPStatus.OK, orjson.dumps(fcm)

    @parse_request
    async def get_collection_items(self, request: AsyncAPIRequest, collection_id: str, item_id: str) -> APIResponse:
        headers = request.get_response_headers(**self.api_headers)
        try:
            request_params = request.params
            if item_id:
                request_params['id'] = item_id

            parameters = parse_query_parameters(CollectionParams(), request_params, self.base_url + "/" +
                                                request.path_info)
            data = await self.provider_part1.query_collection_items(collection_id, parameters)
            return self._format_json_response(request, headers, data, item_id is None)
        except ProviderItemNotFoundError:
            return headers, HTTPStatus.NOT_FOUND, ""

    @parse_request
    async def get(self,
                  request: AsyncAPIRequest,
                  collection: EntityType,
                  path: Path = None
                  ) -> APIResponse:
        """
        Provide Connected Systems API Collections

        :param request: APIRequest instance with query params
        :param collection: Collection to query
        :param path: Additional information extracted from path

        :returns: tuple of headers, status code, content
        """

        allowed_mimetypes = []
        default_mimetype: MimeType = None
        match collection:
            case EntityType.SYSTEMS:
                handler = self.provider_part1.query_systems
                params = SystemsParams()
                allowed_mimetypes = [MimeType.F_HTML, MimeType.F_SMLJSON, MimeType.F_GEOJSON]
                default_mimetype = MimeType.F_SMLJSON
            case EntityType.DEPLOYMENTS:
                handler = self.provider_part1.query_deployments
                params = DeploymentsParams()
                allowed_mimetypes = [MimeType.F_HTML, MimeType.F_SMLJSON, MimeType.F_GEOJSON]
                default_mimetype = MimeType.F_SMLJSON
            case EntityType.PROCEDURES:
                handler = self.provider_part1.query_procedures
                params = ProceduresParams()
                allowed_mimetypes = [MimeType.F_HTML, MimeType.F_SMLJSON, MimeType.F_GEOJSON]
                default_mimetype = MimeType.F_SMLJSON
            case EntityType.SAMPLING_FEATURES:
                handler = self.provider_part1.query_sampling_features
                params = SamplingFeaturesParams()
                allowed_mimetypes = [MimeType.F_HTML, MimeType.F_GEOJSON]
                default_mimetype = MimeType.F_GEOJSON
            case EntityType.PROPERTIES:
                handler = self.provider_part1.query_properties
                params = CSAParams()
                allowed_mimetypes = [MimeType.F_HTML, MimeType.F_SMLJSON]
                default_mimetype = MimeType.F_SMLJSON
            case EntityType.DATASTREAMS:
                handler = self.provider_part2.query_datastreams
                params = DatastreamsParams()
                allowed_mimetypes = [MimeType.F_HTML, MimeType.F_JSON]
                default_mimetype = MimeType.F_JSON
            case EntityType.DATASTREAMS_SCHEMA:
                handler = self.provider_part2.query_datastreams
                params = DatastreamsParams()
                params.schema = True
                allowed_mimetypes = [MimeType.F_JSON]
                default_mimetype = MimeType.F_JSON
            case EntityType.OBSERVATIONS:
                handler = self.provider_part2.query_observations
                params = ObservationsParams()
                allowed_mimetypes = [MimeType.F_HTML, MimeType.F_JSON, MimeType.F_OMJSON]
                default_mimetype = MimeType.F_JSON

        # Check if mime_type is allowed
        if not request.is_valid(allowed_mimetypes):
            return self.get_exception(
                HTTPStatus.BAD_REQUEST,
                {},
                request.format,
                'InvalidMimetype',
                f"invalid mimetype supplied! expected {[f.value for f in allowed_mimetypes]} got '{request.format}'")

        headers = request.get_response_headers(**self.api_headers, default_type=default_mimetype.value, force_type=request.format)
        collection = True
        # Expand parameters with additional information based on path
        if path is not None:
            # Check that id is not malformed.
            if not re.match("^[\\w-]+$", path[1]):
                return self.get_exception(
                    HTTPStatus.BAD_REQUEST,
                    headers,
                    request.format,
                    'InvalidParameterValue',
                    "entity identifer is malformed!")

            # TODO: does the case exist where a property is specified both
            #  in url and query params and we overwrite stuff here?
            request.params[path[0]] = path[1]

            if path[0] == "id":
                collection = False

        if request.format == MimeType.F_HTML.value:
            return self._format_html_response(request, headers, collection)

        try:
            parameters = parse_query_parameters(params, request.params, self.base_url + "/" + request.path_info)
            parameters.format = request.format if request.format is not None else default_mimetype.value
            data = await handler(parameters)

            return self._format_json_response(request, headers, data, collection)
        except ProviderItemNotFoundError:
            return self.get_exception(
                HTTPStatus.NOT_FOUND,
                headers,
                request.format,
                'NotFound',
                "entity not found")
        except ProviderInvalidQueryError as err:
            return self.get_exception(
                HTTPStatus.BAD_REQUEST,
                headers,
                request.format,
                'BadRequest',
                "bad request: " + err.message)

    @parse_request
    async def put(self, request: AsyncAPIRequest, collection: EntityType, path: Path = None):
        return await self._upsert(request, HTTPMethod.PUT, collection, path)

    @parse_request
    async def post(self, request: AsyncAPIRequest, collection: EntityType, path: Path = None):
        return await self._upsert(request, HTTPMethod.POST, collection, path)

    # @parse_request
    # async def patch(self, request: AsyncAPIRequest, collection: EntityType, path: Path = None):
    #    LOGGER.warn("TODO: add validation for properties")
    #    return await self._upsert(request, HTTPMethod.PATCH, collection, path, False)

    @parse_request
    async def delete(self,
                     request: AsyncAPIRequest,
                     collection: EntityType,
                     path: Path = None) -> APIResponse:
        # multiplex provider implementations (part 1 or part 2)
        if (collection == EntityType.OBSERVATIONS
                or collection == EntityType.DATASTREAMS
                or collection == EntityType.DATASTREAMS_SCHEMA):
            provider = self.provider_part2
        else:
            provider = self.provider_part1

        try:
            await provider.delete(collection, path[1], request.params.get("cascade", False))
            return [], HTTPStatus.OK, ""
        except ProviderItemNotFoundError:
            return self.get_exception(
                HTTPStatus.NOT_FOUND,
                request.get_response_headers(**self.api_headers),
                request.format,
                'NotFound',
                "entity not found")
        except ProviderInvalidQueryError as err:
            return self.get_exception(
                HTTPStatus.BAD_REQUEST,
                request.get_response_headers(**self.api_headers),
                request.format,
                'BadRequest',
                "bad request: " + err.message)

    async def _upsert(self,
                      request: AsyncAPIRequest,
                      method: HTTPMethod,
                      collection: EntityType,
                      path: Path = None
                      ) -> APIResponse:

        # multiplex provider implementations (part 1 or part 2)
        strict_validation = True
        if (collection == EntityType.OBSERVATIONS
                or collection == EntityType.DATASTREAMS
                or collection == EntityType.DATASTREAMS_SCHEMA):
            provider = self.provider_part2
            strict_validation = self.strict_validation2
        else:
            provider = self.provider_part1
            strict_validation = self.strict_validation1

        headers = request.get_response_headers(**self.api_headers)
        try:
            entity = orjson.loads(request.data)
        except json.decoder.JSONDecodeError as ex:
            return self.get_exception(
                HTTPStatus.BAD_REQUEST,
                headers,
                request.format,
                'InvalidParameterValue',
                ex.args)
        # Validate against json schema if possible+required
        # must be turned off when PATCHing
        # may be turned off for increased performance
        encoding = request.headers.get("Content-Type")
        if strict_validation:
            try:
                self.validator.validate(collection, encoding, entity)
            except jsonschema.exceptions.ValidationError as ex:
                print(ex)
                return self.get_exception(
                    HTTPStatus.BAD_REQUEST,
                    headers,
                    request.format,
                    'InvalidParameterValue',
                    {
                        "message": ex.message,
                        "context": [e.message for e in ex.context]
                    })
        # remove additional fields that cannot be set using POST/PUT but only through Path but pass validation
        if "parent" in entity:
            return self.get_exception(
                HTTPStatus.BAD_REQUEST,
                headers,
                request.format,
                'InvalidParameterValue',
                "Cannot set parent through request body!")

        if path is not None:
            entity[path[0]] = path[1]

        try:
            # passthru to provider
            match method:
                case HTTPMethod.POST:
                    response = provider.create(collection, encoding, entity)
                case HTTPMethod.PUT:
                    response = provider.replace(collection, encoding, path[1], entity)
                case HTTPMethod.PATCH:
                    response = provider.update(collection, encoding, path[1], entity)
                case _:
                    raise Exception(f"unrecognized HTTMethod {method}")

            result = await response
            return headers, HTTPStatus.CREATED, orjson.dumps(result)
        except Exception as ex:
            return self.get_exception(
                HTTPStatus.BAD_REQUEST,
                headers,
                request.format,
                'InvalidParameterValue',
                ex.args)

    def _format_html_response(self, request, headers, is_collection: bool):
        if is_collection:
            collection = request.collection
            data = {
                "config": {
                    "collection": collection,
                    "backend-url": self.base_url + "/",
                },
                "breadcrumbs": [
                    (collection, "/")
                ]
            }
            if collection in ["subsystems", "datastreams", "deployments"]:
                subcollection = None
                if request.params.get("system"):
                    subcollection = ("system", request.params.get("system"))
                if request.params.get("parent"):
                    subcollection = ("parent", request.params.get("parent"))

                if subcollection:
                    data["config"][subcollection[0]] = subcollection[1]
                    data["breadcrumbs"] = [
                        ("systems", "../"),
                        (subcollection[1], f"../{subcollection[1]}"),
                        (collection, collection)
                    ]
        else:
            collection, id = request.path_info.split("/")
            data = {
                "config": {
                    "collection": collection,
                    "backend-url": self.base_url + "/",
                    "id": id
                },
                "breadcrumbs": [
                    (request.collection, "."),
                    (id, id)
                ]
            }

        data["links"] = [
            {
                "rel": "alternate",
                "type": "application/json",
                "href": "?f=application/json"
            }
        ]
        path = os.path.join(os.path.dirname(__file__), "templates/connected-systems/viewer.html")
        content = render_j2_template(self.tpl_config,
                                     path,
                                     data,
                                     request.locale)
        return headers, HTTPStatus.OK, content

    def _format_json_response(self, request, headers, data, is_collection: bool) -> APIResponse:
        if data is None:
            return headers, HTTPStatus.NOT_FOUND, ""
        match request.format:
            case MimeType.F_GEOJSON.value:
                response = {
                    "type": "FeatureCollection",
                    "features": [item for item in data[0]],
                    "links": [link for link in data[1]],
                } if is_collection else data[0][0]
                return headers, HTTPStatus.OK, orjson.dumps(response)
            case _:
                response = {
                    "items": [item for item in data[0]],
                    "links": [link for link in data[1]],
                } if is_collection else data[0][0]

                return headers, HTTPStatus.OK, orjson.dumps(response)


PLUGINS["provider"]["ElasticSearchConnectedSystems"] = \
    "provider.part1.part1.ConnectedSystemsESProvider"
PLUGINS["provider"]["TimescaleDBConnectedSystems"] = \
    "provider.part2.part2.ConnectedSystemsTimescaleDBProvider"

if not os.getenv("PYGEOAPI_CONFIG"):
    os.environ["PYGEOAPI_CONFIG"] = os.path.join(os.path.dirname(__file__), "default-config.yml")
if not os.getenv("PYGEOAPI_OPENAPI"):
    os.environ["PYGEOAPI_OPENAPI"] = os.path.join(os.path.dirname(__file__), "default-openapi.yml")

LOGGER.critical(f"Loading pygeoapi_config from {os.environ["PYGEOAPI_CONFIG"]}")
LOGGER.critical(f"Loading openapi_config from {os.environ["PYGEOAPI_OPENAPI"]}")

CONFIG = get_config()
OPENAPI = load_openapi_document()

csapi_ = CSAPI(CONFIG, OPENAPI)
