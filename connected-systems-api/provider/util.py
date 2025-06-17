from datetime import datetime as DateTime
from typing import Dict

from elasticsearch_dsl import AttrDict
from pygeoapi.provider.base import ProviderInvalidQueryError


def parse_query_parameters(out_parameters: "CSAParams", input_parameters: Dict, url: str):
    """
    Parse parameter dict into usable/typed parameters
    """

    def _parse_list(identifier):
        setattr(out_parameters,
                identifier,
                [elem for elem in input_parameters.get(identifier).split(",")])

    def _verbatim(key):
        setattr(out_parameters, key, input_parameters.get(key))

    def _parse_int(key):
        setattr(out_parameters, key, int(input_parameters.get(key)))

    def _parse_time(key):
        val = input_parameters.get(key)
        if "/" in val:
            _parse_time_interval(key)
        else:
            # TODO: check if more edge cases/predefined variables exist
            if val == "now":
                date = DateTime.now()
            else:
                date = DateTime.fromisoformat(val)
            setattr(out_parameters, key, (date, date))

    def _parse_bbox(key):
        split = input_parameters.get("bbox").split(',')
        if len(split) == 4:
            box = {
                "type": "2d",
                "x1": split[0],  # Lower left corner, coordinate axis 1
                "x2": split[1],  # Lower left corner, coordinate axis 2
                "y1": split[2],  # Upper right corner, coordinate axis 1
                "y2": split[3]  # Upper right corner, coordinate axis 2
            }
        elif len(split) == 6:
            box = {
                "type": "3d",
                "x1": split[0],  # Lower left corner, coordinate axis 1
                "x2": split[1],  # Lower left corner, coordinate axis 2
                "xalt": split[2],  # Minimum value, coordinate axis 3 (optional)
                "y1": split[3],  # Upper right corner, coordinate axis 1
                "y2": split[4],  # Upper right corner, coordinate axis 2
                "yalt": split[5]  # Maximum value, coordinate axis 3 (optional)
            }
        else:
            raise ProviderInvalidQueryError("invalid bbox")
        setattr(out_parameters, "bbox", box)

    def _parse_time_interval(key):
        raw = input_parameters.get(key)
        setattr(out_parameters, key, raw)
        # TODO: Support 'latest' qualifier
        now = DateTime.now()
        start, end = None, None
        if "/" in raw:
            # time interval
            split = raw.split("/")
            startts = split[0]
            endts = split[1]
            if startts == "now":
                start = now
            elif startts == "..":
                start = None
            else:
                start = DateTime.fromisoformat(startts)
            if endts == "now":
                end = now
            elif endts == "..":
                end = None
            else:
                end = DateTime.fromisoformat(endts)
        else:
            if raw == "now":
                start = now
                end = now
            else:
                ts = DateTime.fromisoformat(raw)
                start = ts
                end = ts
        setattr(out_parameters, "_" + key, (start, end))

    parser = {
        "id": _parse_list,
        "system": _parse_list,
        "parent": _parse_list,
        "q": _verbatim,
        "observedProperty": _parse_list,
        "procedure": _parse_list,
        "controlledProperty": _parse_list,
        "foi": _parse_list,
        "format": _verbatim,
        "f": _verbatim,
        "limit": _parse_int,
        "offset": _parse_int,
        "bbox": _parse_bbox,
        "datetime": _parse_time_interval,
        "geom": _verbatim,
        "datastream": _verbatim,
        "phenomenonTime": _parse_time_interval,
        "resultTime": _parse_time_interval,
    }

    out_parameters._url = url
    #  TODO: There must be a way to make this more efficient/straightforward..
    # Iterate possible parameters
    try:
        for p in out_parameters._parameters:
            # Check if parameter is supplied as input
            if p in input_parameters:
                # Parse value with appropriate mapping function
                parser[p](p)

        return out_parameters
    except Exception as ex:
        raise ProviderInvalidQueryError(user_msg=str(ex.args))


def _format_date_range(key: str, item: AttrDict) -> Dict | None:
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

        return {
            "gte": start,
            "lte": end
        }
    return None
