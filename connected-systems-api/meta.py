import logging
import os
from copy import deepcopy
from http import HTTPStatus

from pygeoapi import l10n
from pygeoapi.api import F_JSONLD, F_JSON, F_HTML, CHARSET, F_GZIP, SYSTEM_LOCALE, FORMAT_TYPES
from pygeoapi.log import setup_logger
from pygeoapi.util import render_j2_template, filter_dict_by_key_value, to_json, get_api_rules, get_base_url, \
    UrlPrefetcher, TEMPLATES

from util import *
from provider.definitions import *

LOGGER = logging.getLogger(__name__)


class CSMeta:
    """
        Provides Meta information about the Connected-Systems API:

        - Implemented Conformance-classes
        - Landingpage
        - Overview-Page
    """

    provider_part1: ConnectedSystemsPart1Provider | None
    provider_part2: ConnectedSystemsPart2Provider | None

    def __init__(self, config, openapi):
        """
        constructor

        :param config: configuration dict
        :param openapi: openapi dict

        :returns: `pygeoapi.API` instance
        """
        self.config = config
        self.openapi = openapi
        self.api_headers = get_api_rules(self.config).response_headers
        self.base_url = get_base_url(self.config)
        self.prefetcher = UrlPrefetcher()

        CHARSET[0] = config['server'].get('encoding', 'utf-8')
        if config['server'].get('gzip'):
            FORMAT_TYPES[F_GZIP] = 'application/gzip'
            FORMAT_TYPES.move_to_end(F_JSON)

        # Process language settings (first locale is default!)
        self.locales = l10n.get_locales(config)
        self.default_locale = self.locales[0]

        if 'templates' not in self.config['server']:
            self.config['server']['templates'] = {'path': TEMPLATES}

        if 'pretty_print' not in self.config['server']:
            self.config['server']['pretty_print'] = False

        self.pretty_print = self.config['server']['pretty_print']

        setup_logger(self.config['logging'])

        # Create config clone for HTML templating with modified base URL
        self.tpl_config = deepcopy(self.config)
        self.tpl_config['server']['url'] = self.base_url

    def get_exception(self, status, headers, format_, code,
                      description) -> Tuple[dict, int, str]:
        """
        Exception handler

        :param status: HTTP status code
        :param headers: dict of HTTP response headers
        :param format_: format string
        :param code: OGC API exception code
        :param description: OGC API exception code

        :returns: tuple of headers, status, and message
        """

        LOGGER.error(description)
        exception = {
            'code': code,
            'type': code,
            'description': description
        }

        if format_ == F_HTML:
            headers['Content-Type'] = FORMAT_TYPES[F_HTML]
            content = render_j2_template(
                self.config, 'exception.html', exception, SYSTEM_LOCALE)
        else:
            if headers is None:
                headers = {}
            headers['Content-Type'] = FORMAT_TYPES[F_JSON]
            content = to_json(exception, self.pretty_print)

        return headers, status, content

    @parse_request
    async def landing(self, request: AsyncAPIRequest) -> APIResponse:
        """
        Provide API landing page

        :param request: A request object

        :returns: tuple of headers, status code, content
        """
        fcm = {
            'links': [],
            'title': l10n.translate(
                self.config['metadata']['identification']['title'],
                request.locale),
            'description':
                l10n.translate(
                    self.config['metadata']['identification']['description'],
                    request.locale)
        }

        # TODO: put title text in config or translatable files?
        fcm['links'] = [{
            'rel': request.get_linkrel(F_JSON),
            'type': FORMAT_TYPES[F_JSON],
            'title': 'This document as JSON',
            'href': f"{self.base_url}?f={F_JSON}"
        }, {
            'rel': request.get_linkrel(F_JSONLD),
            'type': FORMAT_TYPES[F_JSONLD],
            'title': 'This document as RDF (JSON-LD)',
            'href': f"{self.base_url}?f={F_JSONLD}"
        }, {
            'rel': request.get_linkrel(F_HTML),
            'type': FORMAT_TYPES[F_HTML],
            'title': 'This document as HTML',
            'href': f"{self.base_url}?f={F_HTML}",
            'hreflang': self.default_locale
        }, {
            'rel': 'service-desc',
            'type': 'application/vnd.oai.openapi+json;version=3.0',
            'title': 'The OpenAPI definition as JSON',
            'href': f"{self.base_url}/openapi"
        }, {
            'rel': 'service-doc',
            'type': FORMAT_TYPES[F_HTML],
            'title': 'The OpenAPI definition as HTML',
            'href': f"{self.base_url}/openapi?f={F_HTML}",
            'hreflang': self.default_locale
        }, {
            'rel': 'conformance',
            'type': FORMAT_TYPES[F_JSON],
            'title': 'Conformance',
            'href': f"{self.base_url}/conformance"
        }, {
            'rel': 'data',
            'type': FORMAT_TYPES[F_JSON],
            'title': 'Collections',
            'href': f"{self.base_url}/collections"
        }]

        headers = request.get_response_headers(**self.api_headers)
        if request.format == F_HTML:  # render

            fcm['processes'] = False
            fcm['stac'] = False
            fcm['collection'] = False
            fcm['connected-systems'] = False

            if filter_dict_by_key_value(self.config['resources'],
                                        'type', 'process'):
                fcm['processes'] = True

            if filter_dict_by_key_value(self.config['resources'],
                                        'type', 'stac-collection'):
                fcm['stac'] = True

            if filter_dict_by_key_value(self.config['resources'],
                                        'type', 'collection'):
                fcm['collection'] = True

            if filter_dict_by_key_value(self.config['dynamic-resources'],
                                        'type', 'connected-systems-part1'):
                fcm['connected-systems'] = True
                fcm['collection'] = True

            if filter_dict_by_key_value(self.config['dynamic-resources'],
                                        'type', 'connected-systems-part2'):
                fcm['connected-systems'] = True
                fcm['collection'] = True

            path = os.path.join(os.path.dirname(__file__), "templates/landing_page.html")
            content = render_j2_template(self.tpl_config, path,
                                         fcm, request.locale)
            return headers, HTTPStatus.OK, content

        return headers, HTTPStatus.OK, to_json(fcm, self.pretty_print)

    @parse_request
    async def overview(self, request: AsyncAPIRequest) -> APIResponse:
        """
        Provide Connected Systems API root page

        :param request: APIRequest instance with query params

        :returns: tuple of headers, status code, content
        """
        headers = request.get_response_headers(**self.api_headers)

        id_ = 'pygeoapi-csa'
        version = '0.0.1'
        url = f'{self.base_url}'

        content = {
            'id': id_,
            'csa_version': version,
            'title': l10n.translate(
                self.config['metadata']['identification']['title'],
                request.locale),
            'description': l10n.translate(
                self.config['metadata']['identification']['description'],
                request.locale),
            'links': [],
            'endpoints': [],
            'resources': [
                {
                    "collection_name": "systems",
                    "name": "Systems",
                    "description": "Systems are entities that can produce data feeds and/or receive commands (e.g. "
                                   "sensors and sensor networks, platforms, actuators, processing components, "
                                   "etc.). Many systems can be classified as 'observing systems' that produce "
                                   "observations of one or more features of interest.",
                    "specification": "https://opengeospatial.github.io/ogcapi-connected-systems/redoc/?url=../api"
                                     "/part1/openapi/openapi-connectedsystems-1.yaml#tag/Systems"
                },
                {
                    "collection_name": "deployments",
                    "name": "Deployments",
                    "description": "Deployments describe how systems are being deployed at a particular place and time.",
                    "specification": "https://opengeospatial.github.io/ogcapi-connected-systems/redoc/?url=../api"
                                     "/part1/openapi/openapi-connectedsystems-1.yaml#tag/Deployments"
                },
                {
                    "collection_name": "procedures",
                    "name": "Procedures",
                    "description": "Procedures provide information about the behavior of a system to accomplish its "
                                   "task(s). Procedures include descriptions of system kinds (e.g. a hardware "
                                   "device's datasheet), as well as methodologies or specific configurations of these "
                                   "systems (e.g. steps followed by an operator to accomplish a sensing or sampling "
                                   "task).",
                    "specification": "https://opengeospatial.github.io/ogcapi-connected-systems/redoc/?url=../api"
                                     "/part1/openapi/openapi-connectedsystems-1.yaml#tag/Procedures"
                },
                {
                    "collection_name": "samplingFeatures",
                    "name": "Sampling Features",
                    "description": "Sampling Features link Systems with ultimate features of interest, describing "
                                   "exactly what part of a larger feature is being interacted with.",
                    "specification": "https://opengeospatial.github.io/ogcapi-connected-systems/redoc/?url=../api"
                                     "/part1/openapi/openapi-connectedsystems-1.yaml#tag/Sampling-Features"
                },
                {
                    "collection_name": "properties",
                    "name": "Properties",
                    "description": "Property resources provide the definitions of derived properties that are used "
                                   "throughout the API. Derived properties are specific to a type of feature, "
                                   "a type of system, or even to a particular organization, project or deployment. "
                                   "Property definitions are referenced by feature schemas, system and deployment "
                                   "descriptions, datastream and control stream schemas, etc. Depending on the "
                                   "context they are used in, they can represent properties that are asserted (e.g. "
                                   "system characteristic), observed (observed or observable property) or controlled "
                                   "(controlled or controllable property).",
                    "specification": "https://opengeospatial.github.io/ogcapi-connected-systems/redoc/?url=../api"
                                     "/part1/openapi/openapi-connectedsystems-1.yaml#tag/Properties"
                },
                {
                    "collection_name": "datastreams",
                    "name": "Data Streams",
                    "description": "Datastreams allow access to observations produced by systems, in various formats. "
                                   "They also provide metadata describing the exact meaning of properties included in "
                                   "the observations. API clients can act both as sender of receiver of observations.",
                    "specification": "https://opengeospatial.github.io/ogcapi-connected-systems/redoc/?url=../api"
                                     "/part2/openapi/openapi-connectedsystems-2.yaml"
                },
                {
                    "collection_name": "observations",
                    "name": "Observations",
                    "description": "Access to historical and real-time observations.",
                    "specification": "https://opengeospatial.github.io/ogcapi-connected-systems/redoc/?url=../api"
                                     "/part2/openapi/openapi-connectedsystems-2.yaml#tag/Observations"
                }
            ]
        }

        collections = filter_dict_by_key_value(self.config['dynamic-resources'], 'type', 'connected-systems')

        for key, value in collections.items():
            content['links'].append({
                'rel': 'child',
                'href': f'{url}/{key}?f={F_JSON}',
                'type': FORMAT_TYPES[F_JSON]
            })
            content['links'].append({
                'rel': 'child',
                'href': f'{url}/{key}',
                'type': FORMAT_TYPES[F_HTML]
            })

        content['endpoints'].append({
            'title': f'Systems',
            'href': f'{url}/systems?f={FORMAT_TYPES[F_JSON].replace("+", "%2B")}',
            'type': F_JSON,
        })

        content['endpoints'].append({
            'title': f'Systems',
            'href': f'{url}/systems?f={MimeType.F_SMLJSON.value.replace("+", "%2B")}',
            'type': MimeType.F_SMLJSON.value,
        })
        content['endpoints'].append({
            'title': f'Systems',
            'href': f'{url}/systems?f={MimeType.F_GEOJSON.value.replace("+", "%2B")}',
            'type': MimeType.F_GEOJSON.value,
        })
        content['endpoints'].append({
            'title': f'Procedures',
            'href': f'{url}/procedures?f={MimeType.F_GEOJSON.value.replace("+", "%2B")}',
            'type': MimeType.F_GEOJSON.value,
        })
        content['endpoints'].append({
            'title': f'Procedures',
            'href': f'{url}/procedures?f={MimeType.F_SMLJSON.value.replace("+", "%2B")}',
            'type': MimeType.F_SMLJSON.value,
        })

        content['endpoints'].append({
            'title': f'Deployments',
            'href': f'{url}/deployments?f={MimeType.F_GEOJSON.value.replace("+", "%2B")}',
            'type': MimeType.F_GEOJSON.value,
        })
        content['endpoints'].append({
            'title': f'Deployments',
            'href': f'{url}/deployments?f={MimeType.F_SMLJSON.value.replace("+", "%2B")}',
            'type': MimeType.F_SMLJSON.value,
        })

        content['endpoints'].append({
            'title': f'SamplingFeatures',
            'href': f'{url}/samplingFeatures?f={MimeType.F_GEOJSON.value.replace("+", "%2B")}',
            'type': MimeType.F_GEOJSON.value,
        })
        content['endpoints'].append({
            'title': f'Properties',
            'href': f'{url}/properties?f={MimeType.F_SMLJSON.value.replace("+", "%2B")}',
            'type': MimeType.F_SMLJSON.value,
        })
        content['endpoints'].append({
            'title': f'Datastreams',
            'href': f'{url}/datastreams?f={F_JSON.replace("+", "%2B")}',
            'type': F_JSON,
        })
        content['endpoints'].append({
            'title': f'Observations',
            'href': f'{url}/observations?f={MimeType.F_OMJSON.value.replace("+", "%2B")}',
            'type': MimeType.F_OMJSON.value,
        })
        content['endpoints'].append({
            'title': f'Observations',
            'href': f'{url}/observations?f={MimeType.F_SMLJSON.value.replace("+", "%2B")}',
            'type': MimeType.F_SWEJSON.value,
        })

        if request.format == F_HTML:  # render
            path = os.path.join(os.path.dirname(__file__), "templates/connected-systems/overview.html")
            content = render_j2_template(self.tpl_config,
                                         path,
                                         content, request.locale)
            return headers, HTTPStatus.OK, content

        return headers, HTTPStatus.OK, to_json(content, self.pretty_print)

    @parse_request
    async def conformance(self, request: AsyncAPIRequest) -> APIResponse:
        """
        Provide conformance definition

        :param request: A request object

        :returns: tuple of headers, status code, content
        """

        conformance_list = []
        if self.provider_part1:
            conformance_list = self.provider_part1.get_conformance()
        conformance = {
            'conformsTo': list(set(conformance_list))
        }

        headers = request.get_response_headers(**self.api_headers)
        if request.format == F_HTML:  # render
            content = render_j2_template(self.tpl_config, 'conformance.html',
                                         conformance, str(request.locale))
            return headers, HTTPStatus.OK, content

        return headers, HTTPStatus.OK, to_json(conformance, self.pretty_print)
