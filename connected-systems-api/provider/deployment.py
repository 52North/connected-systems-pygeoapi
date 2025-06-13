import logging
from typing import Dict, ClassVar

from elasticsearch_dsl import AsyncDocument, Keyword, GeoShape, Date, InnerDoc, Object, GeoPoint, Text, DateRange, Nested, AttrDict

from provider.definitions import _format_date_range, es_conn_part1
from util import MimeType

LOGGER = logging.getLogger(__name__)


class DeploymentSML(InnerDoc):
    type: str = Keyword()
    id: str = Keyword()
    description = Text()
    uniqueId = Keyword()
    label = Text()
    lang = Text()
    keywords = Text()
    pass


class DeploymentGeoJsonProperties(InnerDoc):
    # Table 39
    uid = Keyword()
    name = Text()
    description = Text()

    # Table 40
    featureType = Keyword()
    assetType = Keyword()
    validTime = Date()


class DeploymentGeoJson(InnerDoc):
    type = Keyword()
    id = Keyword()
    geometry = GeoShape()
    bbox = GeoPoint()
    links = Object()
    properties = DeploymentGeoJsonProperties()


class Deployment(AsyncDocument):
    uid = Keyword()
    linked_system_ids = Keyword()
    validTime = DateRange()
    geometry = GeoShape()
    sml = Nested(DeploymentSML)
    geojson = Nested(DeploymentGeoJson)

    raw: ClassVar[object]
    mime: ClassVar[str]

    class Index:
        name = "deployments"
        using = es_conn_part1

    async def save(self, **kwargs):
        mime: MimeType | None = getattr(self, "mime", None)
        raw: AttrDict | None = getattr(self, "raw", None)
        delattr(self, "mime")
        delattr(self, "raw")

        if "id" not in raw:
            raw["id"] = self.id

        self.validTime = _format_date_range("validTime", raw)
        if mime == MimeType.F_GEOJSON.value:
            LOGGER.error("TODO: transcoding for Deployment")
            self.geojson = DeploymentGeoJson(**raw)
            self.sml = {}
            self.validTime = _format_date_range("validTime", raw["properties"])
            self.geometry = getattr(raw, "geometry", None)
            self.uid = raw["properties"]["uid"]
        elif mime == MimeType.F_SMLJSON.value:
            LOGGER.error("TODO: transcoding for Deployment")
            self.sml = DeploymentSML(**raw)
            self.geojson = deployment_to_geojson(raw.to_dict())
            self.validTime = _format_date_range("validTime", raw)
            self.geometry = getattr(raw, "location", None)
            self.uid = raw["uniqueId"]

        return await super().save(**kwargs)


def deployment_to_geojson(deployment: Dict) -> DeploymentGeoJson:
    # Trancoding according to 23-001r0 Section 19.2.x
    links = deployment.get(f"links") if not None else []
    return DeploymentGeoJson(**{
        "type": "Feature",
        "id": deployment.get("id"),
        "geometry": deployment.get('location'),
        "properties": {
                          ## Required properties as of spec. Always returned
                          "uid": deployment.get("uniqueId"),
                          "name": deployment.get("label"),
                          "featureType": deployment.get("definition"),
                          "validTime": deployment.get("validTime"),
                          "platform@link": deployment.get("platform", {}).get("system"),
                          "deployedSystems@link": deployment.get("deployedSystems"),
                      } | {
                          ## Additional properties that are not defined but may be available. Only returned if defined in source
                          k: v for k, v in [(k, deployment.get(k)) for k in
                                            ["description",
                                             "lang",
                                             "keywords",
                                             "identifiers",
                                             "classifiers",
                                             "securityConstraints",
                                             "legalConstraints",
                                             "characteristics",
                                             "capabilities",
                                             "contacts",
                                             "documents",
                                             "history",
                                             "platform"
                                             ] if deployment.get(k) is not None]
                      },
        "links": links,
    })
