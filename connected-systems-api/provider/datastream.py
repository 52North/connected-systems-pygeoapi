from typing import ClassVar, Text, Optional

from elasticsearch_dsl import AsyncDocument, Keyword, InnerDoc, Object, AttrDict

from provider import es_conn_part2


class DatastreamSchema(InnerDoc):
    obsFormat: str


class Datastream(AsyncDocument):
    uid = Keyword()
    system = Keyword()
    json = Object()
    name: str
    description: Optional[Text]

    raw: ClassVar[object]

    class Index:
        name = "datastreams"
        using = es_conn_part2

    async def save(self, **kwargs):
        raw: AttrDict | None = getattr(self, "raw", None)
        delattr(self, "raw")

        if "id" not in raw:
            raw["id"] = self.id

        self.name = getattr(raw, "name", None)
        self.description = getattr(raw, "description", None)
        self.system = getattr(raw, "system", None)
        self.json = raw

        delattr(raw, "system")

        return await super().save(**kwargs)
