from elasticsearch.dsl import AttrDict
from elasticsearch.dsl import AsyncDocument, Keyword, Object

from provider import es_conn_part1


class Collection(AsyncDocument):
    id = Keyword()
    json = Object()

    class Index:
        name = "collections"
        using = es_conn_part1

    async def save(self, **kwargs):
        raw: AttrDict | None = getattr(self, "raw", None)
        delattr(self, "raw")

        if "id" not in raw:
            raw["id"] = self.id

        self.json = raw

        return await super().save(**kwargs)
