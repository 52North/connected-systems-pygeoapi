from enum import Enum
from typing import Self, Union, Tuple, Optional, List, OrderedDict

from pygeoapi import l10n
from pygeoapi.api import APIRequest, SYSTEM_LOCALE, FORMAT_TYPES
from quart import make_response, Quart, Request
from werkzeug.datastructures import MultiDict

APIResponse = Tuple[dict | None, int, str]
Path = Union[Tuple[str, str], None]


class MimeType(Enum):
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
    collection = str


class CustomQuart(Quart):
    request_class = ModifiableRequest
    metrics: AppState


F_GEOJSON = 'geojson'
F_SMLJSON = 'smljson'
F_OMJSON = 'omjson'
F_SWEJSON = 'swejson'


class AsyncAPIRequest(APIRequest):
    CSAFORMAT_TYPES = OrderedDict((
        (F_GEOJSON, "application/geo+json"),
        (F_SMLJSON, "application/sml+json"),
        (F_OMJSON, "application/om+json"),
        (F_SWEJSON, "application/swe+json"),
        ("application/geo+json", "application/geo+json"),
        ("application/sml+json", "application/sml+json"),
        ("application/om+json", "application/om+json"),
        ("application/swe+json", "application/swe+json")
    )) | FORMAT_TYPES

    @classmethod
    async def from_request(cls, request: Union[ModifiableRequest, Request], supported_locales=None) -> Self:
        if supported_locales is None:
            supported_locales = [SYSTEM_LOCALE]
        api_req = cls(request, supported_locales)
        api_req._data = await request.data
        if request.collection:
            api_req.collection = request.collection
        return api_req

    def is_valid(self, allowed_formats: Optional[list[str]] = None) -> bool:
        if self._format in self.CSAFORMAT_TYPES.keys():
            return True
        return super().is_valid(additional_formats=allowed_formats)

    def _get_format(self, headers) -> Union[str, None]:
        # Optional f=html or f=json query param
        # Overrides Accept header and might differ from FORMAT_TYPES
        format_ = (self._args.get('f') or '').strip()
        if format_:
            # We also allow specifying the full type (e.g. f=application/json)
            if format_.startswith("application/"):
                return format_[12:].replace("+", "").replace(" ", "")
            return format_

        # Format not specified: get from Accept headers (MIME types)
        # e.g. format_ = 'text/html'
        h = headers.get('accept', headers.get('Accept', '')).strip()  # noqa
        (fmts, mimes) = zip(*self.CSAFORMAT_TYPES.items())

        # basic support for complex types (i.e. with "q=0.x")
        for type_ in (t.split(';')[0].strip() for t in h.split(',') if t):
            if type_ in mimes:
                idx_ = mimes.index(type_)
                format_ = fmts[idx_]
                break

        return format_ or None

    def get_response_headers(self, force_lang: l10n.Locale = None,
                             default_type: str = None,
                             force_type: str = None,
                             **custom_headers) -> dict:
        
        content_type = self.CSAFORMAT_TYPES[default_type] if default_type and default_type in self.CSAFORMAT_TYPES else None
        if force_type and force_type in self.CSAFORMAT_TYPES:
            content_type = self.CSAFORMAT_TYPES[force_type]
        elif self._format and self._format in self.CSAFORMAT_TYPES:
            content_type = self.CSAFORMAT_TYPES[self._format]

        response_headers = {
            'Content-Type': content_type,
            # 'X-Powered-By': f'pygeoapi {__version__}',
        }
        print(f"response_headers: {response_headers}")
        return response_headers


def parse_request(func):
    async def inner(*args):
        cls, req_in = args[:2]
        req_out = await AsyncAPIRequest.from_request(req_in, getattr(cls, 'locales'))
        if len(args) > 2:
            return await func(cls, req_out, *args[2:])
        else:
            return await func(cls, req_out)

    return inner


async def to_response(result: APIResponse):
    """
    Creates a Quart Response object and updates matching headers.

    :param result: The result of the API call.
                   This should be a tuple of (headers, status, content).

    :returns: A Response instance.
    """
    return await make_response(result[2], result[1], result[0])
