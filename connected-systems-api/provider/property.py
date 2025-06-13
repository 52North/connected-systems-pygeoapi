from elasticsearch_dsl import Keyword, AsyncDocument

from provider import es_conn_part1


class Property(AsyncDocument):
    id: str = Keyword()

    class Index:
        name = "properties"
        using = es_conn_part1
