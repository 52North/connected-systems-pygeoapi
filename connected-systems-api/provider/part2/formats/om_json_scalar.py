from datetime import datetime as DateTime

import asyncpg
import orjson

from ..util import SchemaParser, Observation


class OMJsonSchemaParser(SchemaParser):

    def decode(self, data: any) -> Observation:
        obs = Observation(
            datastream_id=data["datastream"],
            resultTime=DateTime.fromisoformat(data["resultTime"]),
            result=orjson.dumps(data["result"]).decode("utf-8"),
        )
        #if not provided phenomenon time equals result time by default
        obs.phenomenonTime = DateTime.fromisoformat(data["phenomenonTime"]) if "phenomenonTime" in data else obs.resultTime

        return obs

    def encode(self, obs: asyncpg.Record) -> any:
        # TODO(specki): Check what is officially required here, e.g. are datastream@link or foi@link necessary?

        # unpack always returns tuple for consistency
        obs_json =  {
            "id": str(obs["uuid"]),
            "datastream@id": str(obs["datastream_id"]),
            "resultTime": obs["resulttime"],
            "result": orjson.loads(obs["result"])
        }

        if obs["phenomenontime"] is not None:
            obs_json["phenomenonTime"] = obs["phenomenontime"]

        return obs_json
