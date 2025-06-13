from typing import Dict

from elasticsearch_dsl import AsyncDocument, Keyword, GeoShape, Date, DateRange, InnerDoc, Object, GeoPoint, Text, Nested, AttrDict
from pygeoapi.provider.base import ProviderInvalidQueryError

from provider.definitions import _format_date_range, es_conn_part1
from util import MimeType


class CharacteristicsProp(InnerDoc):
    value = Keyword()


class Characteristics(InnerDoc):
    characteristics = CharacteristicsProp()


class SystemSML(InnerDoc):
    type: str = Keyword()
    id: str = Keyword()
    description = Text()
    uniqueId = Keyword()
    label = Text()
    lang = Text()
    keywords = Text()
    position = GeoShape()
    parent = Keyword()
    procedure = Keyword()
    poi = Keyword()
    observedProperty = Keyword()
    controlledProperty = Keyword()
    characteristics = Characteristics()


class SystemGeoJsonProperties(InnerDoc):
    featureType = Keyword()
    uid = Keyword()
    name = Text()
    description = Text()
    assetType = Keyword()
    validTime = Date()


class SystemGeoJson(InnerDoc):
    type = Keyword()
    id = Keyword()
    geometry = GeoShape()
    bbox = GeoPoint()
    links = Object()
    properties = SystemGeoJsonProperties()


class System(AsyncDocument):
    """
    Meta-Keywords used for filtering. Must be supported by all encodings
    """
    # _type: str = Keyword()
    parent = Keyword()
    uid = Keyword()
    validTime = DateRange()
    geometry = GeoShape()

    sml = Nested(SystemSML)
    geojson = Nested(SystemGeoJson)

    class Index:
        name = "systems"
        using = es_conn_part1

    async def save(self, **kwargs):
        mime: MimeType | None = getattr(self, "mime", None)
        raw: AttrDict | None = getattr(self, "raw", None)
        delattr(self, "mime")
        delattr(self, "raw")

        if "id" not in raw:
            raw["id"] = self.id

        if mime == MimeType.F_GEOJSON.value:
            self.geojson = SystemGeoJson(**raw)
            self.sml = system_to_sml(raw)
            self.validTime = _format_date_range("validTime", raw["properties"])
            self.geometry = raw["geometry"]
            self.uid = raw["properties"]["uid"]
        elif mime == MimeType.F_SMLJSON.value:
            self.sml = SystemSML(**raw)
            self.geojson = system_to_geojson(raw.to_dict())
            self.validTime = _format_date_range("validTime", raw)
            self.geometry = getattr(raw, "position", None)
            self.uid = raw.uniqueId

        await super().save(**kwargs)


def system_to_sml(system: Dict) -> SystemSML:
    if system.get("_type") == "geojson":
        raise ProviderInvalidQueryError(user_msg=f"transcoding  GeoJSON to SensorML is not yet supported!")
    return {}


def system_to_geojson(system: Dict) -> SystemGeoJson:
    # Trancoding according to 23-001r0 Section 19.2.x
    links = system.get(f"links") if not None else []
    if system.get("attachedTo"):
        links.append(system.get("attachedTo"))
    return SystemGeoJson(**{
        "type": "Feature",
        "id": system.get("id"),
        "properties": {
                          ## Required properties as of spec. Always returned
                          "uid": system.get("uniqueId"),
                          "name": system.get("label"),
                          "description": system.get("description"),
                          "featureType": system.get("systemType"),
                          "assetType": system.get("classifiers"),
                          "validTime": system.get("validTime"),
                          "systemKind@link": system.get("typeOf"),
                      } | {
                          ## Additional properties that are not defined but may be available. Only returned if defined in source
                          k: v for k, v in [(k, system.get(k)) for k in
                                            ["identifiers",
                                             "contacts",
                                             "lang",
                                             "keywords",
                                             "identifiers",
                                             "securityConstraints",
                                             "legalConstraints",
                                             "characteristics",
                                             "capabilities",
                                             "contacts",
                                             "documents",
                                             "history",
                                             "configuration",
                                             "featuresOfInterest",
                                             "inputs",
                                             "outputs",
                                             "parameters",
                                             "modes",
                                             "method",
                                             "components"
                                             ] if system.get(k) is not None]
                      },
        "geometry": system.get("position"),
        "links": links,
    })
