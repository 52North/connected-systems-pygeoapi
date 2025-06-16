import logging
from typing import Dict

from elasticsearch_dsl import Keyword, GeoShape, Date, InnerDoc, Object, GeoPoint, Text, Nested

from provider.definitions import es_conn_part1, CSDocument
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


class Deployment(CSDocument):
    linked_system_ids = Keyword()
    geometry = GeoShape()
    sml = Nested(DeploymentSML)
    geojson = Nested(DeploymentGeoJson)

    class Index:
        name = "deployments"
        using = es_conn_part1

    async def save(self, **kwargs):
        if "id" not in self.raw:
            self.raw["id"] = self.id

        if self.mime == MimeType.F_GEOJSON.value:
            LOGGER.error("TODO: transcoding for Deployment")
            self.geojson = DeploymentGeoJson(**self.raw)
            self.sml = {}
            self.geometry = getattr(self.raw, "geometry", None)
        elif self.mime == MimeType.F_SMLJSON.value:
            LOGGER.error("TODO: transcoding for Deployment")
            self.sml = DeploymentSML(**self.raw)
            self.geojson = deployment_to_geojson(self.raw.to_dict())
            self.geometry = getattr(self.raw, "location", None)

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
