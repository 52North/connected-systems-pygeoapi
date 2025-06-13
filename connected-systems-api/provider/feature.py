from elasticsearch_dsl import AsyncDocument, Keyword

from provider import es_conn_part1


class SamplingFeature(AsyncDocument):
    id: str = Keyword()
    system_ids = Keyword()  # Internal field

    class Index:
        name = "sampling_features"
        using = es_conn_part1
