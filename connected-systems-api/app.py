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
import os.path
import secrets

from pygeoapi import static
from quart import request, send_from_directory
from quart_auth import basic_auth_required
from quart_cors import cors

from api import *
from routes.collections import collections
from routes.coverages import coverage
from routes.csa import csa_read, csa_readwrite
from routes.edr import edr
from routes.processes import oapip
from routes.stac import stac

APP = CustomQuart(__name__,
                  static_folder=static.__path__._path[0],
                  static_url_path='/static')
APP.metrics = AppState(version="0.1")

APP.config['QUART_CORS_ALLOW_ORIGIN'] = os.environ.get("CSA_CORS_ALLOW_ORIGIN") or ""
APP.config['QUART_CORS_ALLOW_CREDENTIALS'] = os.environ.get("CSA_CORS_ALLOW_CREDENTIALS")
APP.config['QUART_CORS_ALLOW_METHODS'] = os.environ.get("CSA_CORS_ALLOW_METHODS")
APP.config['QUART_CORS_ALLOW_HEADERS'] = os.environ.get("CSA_CORS_ALLOW_HEADERS")
APP.config['QUART_CORS_EXPOSE_HEADERS'] = os.environ.get("CSA_CORS_EXPOSE_HEADERS")
APP.config['QUART_CORS_MAX_AGE'] = os.environ.get("CSA_CORS_MAX_AGE")
APP = cors(APP)

APP.config["QUART_AUTH_BASIC_USERNAME"] = os.environ.get("QUART_AUTH_BASIC_USERNAME") or secrets.token_hex()
APP.config["QUART_AUTH_BASIC_PASSWORD"] = os.environ.get("QUART_AUTH_BASIC_PASSWORD") or secrets.token_hex()
APP.config["QUART_AUTH_BASIC_READ"] = os.environ.get("QUART_AUTH_BASIC_READ") or False
APP.config["QUART_AUTH_BASIC_READWRITE"] = os.environ.get("QUART_AUTH_BASIC_READWRITE") or True

APP.url_map.strict_slashes = False
APP.config['JSONIFY_PRETTYPRINT_REGULAR'] = CONFIG['server'].get('pretty_print', False)

if APP.config["QUART_AUTH_BASIC_READ"]:
    @csa_read.before_request
    @basic_auth_required()
    async def is_auth():
        # Auth is handled by @basic_auth_required wrapper already
        return None


    @collections.before_request
    @basic_auth_required()
    async def is_auth():
        # Auth is handled by @basic_auth_required wrapper already
        return None

if APP.config["QUART_AUTH_BASIC_READWRITE"]:
    @csa_readwrite.before_request
    @basic_auth_required()
    async def is_auth():
        # Auth is handled by @basic_auth_required wrapper already
        return None

if APP.metrics.state == State.STARTING:
    APP.register_blueprint(csa_read)
    APP.register_blueprint(csa_readwrite)

    # TODO: make this configurable, only import required/configured
    # APP.register_blueprint(edr)
    # APP.register_blueprint(stac)
    # APP.register_blueprint(oapip)
    # APP.register_blueprint(coverage)
    APP.register_blueprint(collections)


@APP.get('/')
async def landing_page():
    request.collection = ""
    return await to_response(await csapi_.landing(request))


@basic_auth_required()
@APP.get('/metrics')
async def metrics():
    headers = {"Content-Type": "text/plain"}
    return await make_response(str(APP.metrics), headers)

@basic_auth_required()
@APP.get('/status')
async def status():
    match APP.metrics.state.value:
        case State.RUNNING:
            code = HTTPStatus.OK
        case _:
            code = HTTPStatus.INTERNAL_SERVER_ERROR

    return await make_response("", code)


@APP.get('/assets/<path:filename>')
async def assets(filename):
    request.collection = None
    abspath = os.path.join(os.path.dirname(__file__), "templates/connected-systems/assets")
    return await send_from_directory(abspath, filename)


@APP.get('/openapi')
async def openapi():
    from pygeoapi import flask_app
    request.collection = None
    return flask_app.openapi()


@APP.get('/conformance')
async def conformance():
    request.collection = None
    return await to_response(await csapi_.conformance(request))


@APP.before_serving
async def init_db():
    """ Initialize persistent database/provider connections """
    try:
        if csapi_.provider_part1:
            await csapi_.provider_part1.open()
            await csapi_.provider_part1.setup()
        if csapi_.provider_part2:
            await csapi_.provider_part2.open()
            await csapi_.provider_part2.setup()
    except Exception as e:
        LOGGER.error(e)
        APP.metrics.state = State.ERROR
        return

    APP.metrics.state = State.RUNNING


@APP.after_serving
async def close_db():
    """ Clean exit database/provider connections """
    if csapi_.provider_part1:
        await csapi_.provider_part1.close()
    if csapi_.provider_part2:
        await csapi_.provider_part2.close()


if __name__ == "__main__":
    for _ in range(5):
        LOGGER.critical("!!! RUNNING IN DEBUG MODE !!! ")

    """ Initialize peristent database/provider connections """
    APP.metrics.mode = AppMode.DEV
    APP.run(debug=True, host="localhost", port=5000)
