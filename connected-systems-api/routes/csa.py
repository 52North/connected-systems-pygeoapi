from quart import request, Blueprint

from api import csapi_
from provider.definitions import *
from util import *

csa_readwrite = Blueprint('csa_readwrite', __name__)
csa_read = Blueprint('csa_read', __name__)


@csa_read.route('/connected-systems/')
async def csa_catalog_root():
    request.collection = None
    """
    Connected Systems API root endpoint

    :returns: HTTP response
    """
    return await to_response(await csapi_.overview(request))


@csa_read.route('/systems', methods=['GET'])
@csa_read.route('/systems/<path:path>', methods=['GET'])
@csa_readwrite.route('/systems', methods=['GET', 'POST'])
@csa_readwrite.route('/systems/<path:path>', methods=['GET', 'PUT', 'DELETE'])
async def systems_path(path=None):
    request.collection = "systems"
    return await _default_handler(path, EntityType.SYSTEMS)


@csa_read.route('/procedures', methods=['GET'])
@csa_read.route('/procedures/<path:path>', methods=['GET'])
@csa_readwrite.route('/procedures', methods=['GET', 'POST'])
@csa_readwrite.route('/procedures/<path:path>', methods=['GET', 'PUT', 'DELETE'])
async def procedures_path(path=None):
    request.collection = "procedures"
    return await _default_handler(path, EntityType.PROCEDURES)


@csa_read.route('/systems/<path:path>/subsystems', methods=['GET'])
@csa_read.route('/systems/<path:path>/deployments', methods=['GET'])
@csa_read.route('/systems/<path:path>/samplingFeatures', methods=['GET'])
@csa_read.route('/systems/<path:path>/datastreams', methods=['GET'])
@csa_readwrite.route('/systems/<path:path>/subsystems', methods=['GET', 'POST'])
@csa_readwrite.route('/systems/<path:path>/deployments', methods=['GET'])
@csa_readwrite.route('/systems/<path:path>/samplingFeatures', methods=['GET', 'POST'])
@csa_readwrite.route('/systems/<path:path>/datastreams', methods=['GET', 'POST'])
async def systems_subpath(path=None):
    collection = request.path.split('/')[-1]
    request.collection = collection
    if request.method == 'GET':
        match collection:
            case "subsystems":
                return await to_response(await csapi_.get(request, EntityType.SYSTEMS, ("parent", path)))
            case "deployments":
                return await to_response(await csapi_.get(request, EntityType.DEPLOYMENTS, ("system", path)))
            case "samplingFeatures":
                return await to_response(await csapi_.get(request, EntityType.SAMPLING_FEATURES, ("system", path)))
            case "datastreams":
                return await to_response(await csapi_.get(request, EntityType.DATASTREAMS, ("system", path)))
    elif request.method == 'POST':
        match collection:
            case "subsystems":
                return await to_response(await csapi_.post(request, EntityType.SYSTEMS, ("parent", path)))
            case "samplingFeatures":
                return await to_response(await csapi_.post(request, EntityType.SAMPLING_FEATURES, ("system", path)))
            case "datastreams":
                return await to_response(await csapi_.post(request, EntityType.DATASTREAMS, ("system", path)))


@csa_read.route('/deployments', methods=['GET'])
@csa_read.route('/deployments/<path:path>', methods=['GET'])
@csa_readwrite.route('/deployments', methods=['GET', 'POST'])
@csa_readwrite.route('/deployments/<path:path>', methods=['GET', 'PUT', 'DELETE'])
async def deployments_path(path=None):
    request.collection = "deployments"
    return await _default_handler(path, EntityType.DEPLOYMENTS)


@csa_read.route('/samplingFeatures', methods=['GET'])
@csa_read.route('/samplingFeatures/<path:path>', methods=['GET'])
@csa_readwrite.route('/samplingFeatures', methods=['GET', 'PUT', 'DELETE'])
@csa_readwrite.route('/samplingFeatures/<path:path>', methods=['GET', 'PUT', 'DELETE'])
async def properties_path(path=None):
    request.collection = "samplingFeatures"
    return await _default_handler(path, EntityType.SAMPLING_FEATURES)


@csa_read.route('/properties', methods=['GET'])
@csa_read.route('/properties/<path:path>', methods=['GET'])
@csa_readwrite.route('/properties', methods=['GET', 'PUT', 'DELETE'])
@csa_readwrite.route('/properties/<path:path>', methods=['GET', 'PUT', 'DELETE'])
async def properties_subpath(path=None):
    request.collection = "properties"
    return await _default_handler(path, EntityType.PROPERTIES)


@csa_read.route('/datastreams', methods=['GET'])
@csa_read.route('/datastreams/<path:path>', methods=['GET'])
@csa_readwrite.route('/datastreams', methods=['GET', 'PUT', 'DELETE'])
@csa_readwrite.route('/datastreams/<path:path>', methods=['GET', 'PUT', 'DELETE'])
async def datastreams_path(path=None):
    request.collection = "datastreams"
    return await _default_handler(path, EntityType.DATASTREAMS)


@csa_read.route('/datastreams/<path:path>/schema', methods=['GET'])
@csa_readwrite.route('/datastreams/<path:path>/schema', methods=['GET', 'PUT'])
async def datastreams_schema(path=None):
    request.collection = "schema"
    if request.method == 'GET':
        return await to_response(await csapi_.get(request, EntityType.DATASTREAMS_SCHEMA, ("id", path)))
    else:
        return await to_response(await csapi_.put(request, EntityType.DATASTREAMS_SCHEMA, ("id", path)))


@csa_read.route('/datastreams/<path:path>/observations', methods=['GET'])
@csa_readwrite.route('/datastreams/<path:path>/observations', methods=['GET', 'POST'])
async def datastreams_observations(path=None):
    request.collection = "observations"
    if request.method == 'GET':
        return await to_response(await csapi_.get(request, EntityType.OBSERVATIONS, ("datastream", path)))
    else:
        return await to_response(await csapi_.post(request, EntityType.OBSERVATIONS, ("datastream", path)))


@csa_read.route('/observations', methods=['GET'])
@csa_read.route('/observations/<path:path>', methods=['GET'])
@csa_readwrite.route('/observations', methods=['GET'])
@csa_readwrite.route('/observations/<path:path>', methods=['GET', 'PUT', 'DELETE'])
async def observations_path(path=None):
    request.collection = "observations"
    return await _default_handler(path, EntityType.OBSERVATIONS)


async def _default_handler(path, entity_type):
    match request.method:
        case "GET":
            if path is not None:
                return await to_response(await csapi_.get(request, entity_type, ("id", path)))
            else:
                return await to_response(await csapi_.get(request, entity_type))
        case "PATCH":
            return await to_response(await csapi_.patch(request, entity_type, ("id", path)))
        case "POST":
            return await to_response(await csapi_.post(request, entity_type))
        case "PUT":
            return await to_response(await csapi_.put(request, entity_type, ("id", path)))
        case "DELETE":
            return await to_response(await csapi_.delete(request, entity_type, ("id", path)))
