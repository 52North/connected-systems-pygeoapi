from enum import Enum
from typing import Self, Union, Tuple, Optional

from pygeoapi import l10n
from pygeoapi.api import APIRequest

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
        return [self.F_HTML, self.F_GEOJSON, self.F_SMLJSON, self.F_OMJSON, self.F_SWEJSON]


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