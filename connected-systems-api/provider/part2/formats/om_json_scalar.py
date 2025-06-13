from datetime import datetime as DateTime

import asyncpg
import orjson

from ..util import SchemaParser, Observation


class OMJsonSchemaParser(SchemaParser):

    def decode(self, data: any) -> Observation:
        return Observation(
            datastream_id=data["datastream"],
            resultTime=DateTime.fromisoformat(data["resultTime"]),
            result=orjson.dumps(data["result"]),
        )

    def encode(self, obs: asyncpg.Record) -> any:
        # TODO(specki): Check what is officially required here, e.g. are datastream@link or foi@link necessary?

        # unpack always returns tuple for consistency
        return {
            "id": str(obs["uuid"]),
            "datastream@id": str(obs["datastream_id"]),
            "resultTime": obs["resulttime"],
            "result": orjson.loads(obs["result"])
        }
