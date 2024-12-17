from dataclasses import dataclass
from enum import Enum, auto
from typing import Self, Union, Tuple, Optional, List

from pygeoapi import l10n
from pygeoapi.api import APIRequest
from quart import make_response, Quart, Request
from werkzeug.datastructures import MultiDict

APIResponse = Tuple[dict | None, int, str]
Path = Union[Tuple[str, str], None]


class ALLOWED_MIMES(Enum):
    F_HTML = "html"
    F_JSON = "application/json"
    F_GEOJSON = "application/geo+json"
    F_SMLJSON = "application/sml+json"
    F_OMJSON = "application/om+json"
    F_SWEJSON = "application/swe+json"

    def all(self):
        return [self.F_HTML, self.F_JSON, self.F_GEOJSON, self.F_SMLJSON, self.F_OMJSON,
                self.F_SWEJSON]

    @classmethod
    def values(cls):
        return [cls.F_HTML.value, cls.F_JSON.value, cls.F_GEOJSON.value, cls.F_SMLJSON.value,
                cls.F_OMJSON.value, cls.F_SWEJSON.value]


class State(str, Enum):
    STARTING = "starting"
    RUNNING = "running"
    DEGRADED = "degraded"
    ERROR = "error"


class AppMode(str, Enum):
    PROD = "prod"
    DEV = "dev"


class AppState:
    mode: AppMode = AppMode.PROD
    state: State = State.STARTING
    enabled_specs: List
    _version: str

    def __init__(self, version: str):
        self._version = version

    def __repr__(self):
        return f"""# HELP version
# TYPE csapi_meta info
csapi_meta_info{{version={self._version}, mode={self.mode}}} 1 
"""


# makes request args modifiable
class ModifiableRequest(Request):
    dict_storage_class = MultiDict
    parameter_storage_class = MultiDict


class CustomQuart(Quart):
    request_class = ModifiableRequest
    metrics: AppState


class AsyncAPIRequest(APIRequest):
    @classmethod
    async def with_data(cls, request, supported_locales) -> Self:
        api_req = cls(request, supported_locales)
        api_req._data = await request.data
        if request.collection:
            api_req.collection = request.collection
        return api_req

    def is_valid(self, allowed_formats: Optional[list[str]] = None) -> bool:
        if self._format in (f.value.lower() for f in (allowed_formats or ())):
            return True
        return False

    def _get_format(self, headers) -> Union[str, None]:
        if f := super()._get_format(headers):
            return "application/json" if f == "json" else f
        else:
            h = headers.get('accept', headers.get('Accept', '')).strip()  # noqa
            return h if h in ALLOWED_MIMES.values() else None

    def get_response_headers(self, force_lang: l10n.Locale = None,
                             force_type: str = None,
                             force_encoding: str = None,
                             **custom_headers) -> dict:
        return {
            'Content-Type': force_encoding if force_encoding else self._format,
            # 'X-Powered-By': f'pygeoapi {__version__}',
        }


def parse_request(func):
    async def inner(*args):
        cls, req_in = args[:2]
        req_out = await AsyncAPIRequest.with_data(req_in, getattr(cls, 'locales', set()))
        if len(args) > 2:
            return await func(cls, req_out, *args[2:])
        else:
            return await func(cls, req_out)

    return inner


class CompatibilityRequest:
    data = None
    headers = None
    args = None

    def __init__(self, data, headers, args):
        self.data = data
        self.headers = headers
        self.args = args


async def to_response(result: APIResponse):
    """
    Creates a Quart Response object and updates matching headers.

    :param result: The result of the API call.
                   This should be a tuple of (headers, status, content).

    :returns: A Response instance.
    """
    return await make_response(result[2], result[1], result[0])
