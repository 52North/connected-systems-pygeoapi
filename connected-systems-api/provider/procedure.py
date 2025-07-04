import logging
from typing import Dict

from elasticsearch_dsl import Keyword, GeoShape, InnerDoc, Object, Text, Nested

from provider.definitions import es_conn_part1, CSDocument
from util import MimeType

LOGGER = logging.getLogger(__name__)


class ProcedureSML(InnerDoc):
    type: str = Keyword()
    procedureType: str = Keyword()
    id: str = Keyword()
    description = Text()
    uniqueId = Keyword()
    label = Text()
    lang = Text()
    keywords = Text()


class ProcedureGeoJson(InnerDoc):
    type = Keyword()
    id = Keyword()
    geometry = GeoShape()
    links = Object()
    properties = Object()


class Procedure(CSDocument):
    sml = Nested(ProcedureSML)
    geojson = Nested(ProcedureGeoJson)

    class Index:
        name = "procedures"
        using = es_conn_part1

    async def save(self, **kwargs):
        if "id" not in self.raw:
            self.raw["id"] = self.id

        if self.mime == MimeType.F_GEOJSON.value:
            LOGGER.warning("TODO: transcode Procedure GeoJSON -> SML")
            self.geojson = ProcedureGeoJson(**self.raw)
            self.sml = {}
        elif self.mime == MimeType.F_SMLJSON.value:
            self.sml = ProcedureSML(**self.raw)
            self.geojson = procedure_to_geojson(self.raw.to_dict())

        await super().save(**kwargs)


def procedure_to_geojson(procedure: Dict) -> ProcedureGeoJson:
    # Trancoding according to 23-001r0 Section 19.2.x
    links = procedure.get(f"links") if not None else []
    return ProcedureGeoJson(**{
        "type": "Feature",
        "id": procedure.get("id"),
        "properties": {
                          ## Required properties as of spec. Always returned
                          "uid": procedure.get("uniqueId"),
                          "name": procedure.get("label"),
                          "description": procedure.get("description"),
                          "featureType": procedure.get("procedureType"),
                          "validTime": procedure.get("validTime"),
                      } | {
                          ## Additional properties that are not defined but may be available. Only returned if defined in source
                          k: v for k, v in [(k, procedure.get(k)) for k in
                                            ["lang",
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
                                             "typeOf",
                                             "configuration",
                                             "featuresOfInterest",
                                             "inputs",
                                             "outputs",
                                             "parameters",
                                             "modes",
                                             "method",
                                             ] if procedure.get(k) is not None]
                      },
        "geometry": None,
        "links": links,
    })
