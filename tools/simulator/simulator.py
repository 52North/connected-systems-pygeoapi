import random
import uuid
from datetime import datetime as DateTime
from typing import Dict

import requests
from requests.auth import HTTPBasicAuth
from tqdm import tqdm

last_result = 10

# url_stub = "http://connected-systems.docker.srv.int.52north.org"
url_stub = "http://localhost:5000"
num_of_obs_to_insert = 1_000_000

THREAD_POOL = 16

# This is how to create a reusable connection pool with python requests.
session = requests.Session()
session.mount(
    'https://',
    requests.adapters.HTTPAdapter(pool_maxsize=THREAD_POOL,
                                  max_retries=3,
                                  pool_block=True)
)


def post(path: str, payload: dict, content_type: str = "application/json"):
    url = url_stub + path
    headers = {"Content-Type": content_type}
    basic = HTTPBasicAuth('test', 'test')
    response = requests.request("POST", url, json=payload, headers=headers, auth=basic)
    if response.status_code != 201:
        print(response)
        print(response.text)


def gen_observation(datastream_id: str) -> dict:
    # see https://docs.ogc.org/DRAFTS/23-002r0.html#clause-json-observation
    # example:
    # {
    #   "id": "1h6pmb3ntfmogfppknk9aefpvs",
    #   "datastream@id": "958tf25kjm2f6",
    #   "phenomenonTime": "2021-03-15T04:53:34Z",
    #   "resultTime": "2021-03-15T04:53:34Z",
    #   "result": 23.5
    # }
    global last_result
    last_result = last_result + random.uniform(-0.15, 0.15)
    return {
        "id": str(uuid.uuid4()),
        "datastream@id": datastream_id,
        "resultTime": DateTime.now().isoformat(),
        "result": last_result
    }


def gen_system():
    id = str(uuid.uuid4())
    return {
        "type": "PhysicalSystem",
        "id": id,
        "definition": "http://www.w3.org/ns/sosa/Sensor",
        "uniqueId": f"urn:x-ogc:systems:{id}",
        "label": "Outdoor Thermometer 001",
        "description": "Digital thermometer located on first floor window 1",
        "typeOf": {
            "href": "https://data.example.org/api/procedures/TP60S?f=sml",
            "uid": "urn:x-myorg:datasheets:ThermoPro:TP60S:v001",
            "title": "ThermoPro TP60S",
            "type": "application/sml+json"
        },
        "identifiers": [
            {
                "definition": "http://sensorml.com/ont/swe/property/SerialNumber",
                "label": "Serial Number",
                "value": "0123456879"
            }
        ],
        "contacts": [
            {
                "role": "http://sensorml.com/ont/swe/roles/Operator",
                "organisationName": "Field Maintenance Corp."
            }
        ],
        "validTime": [
            "2019-08-24T14:15:22Z",
            "2025-08-24T17:15:22Z"
        ],
        "position": {
            "type": "Point",
            "coordinates": [
                51.935814, 7.651898
            ]
        }
    }


def gen_datastream(system: Dict):
    return {
        "id": str(uuid.uuid4()),
        "name": "Indoor Thermometer 001 - Living Room Temperature",
        "description": "Indoor temperature measured on the south wall of the living room at 1.5m above the floor",
        "ultimateFeatureOfInterest@link": {
            "href": "https://data.example.org/api/collections/buildings/items/754",
            "title": "My House"
        },
        "samplingFeature@link": {
            "href": "https://data.example.org/api/samplingFeatures/4478",
            "title": "Thermometer Sampling Point"
        },
        "system@link": {
            "href": f"{url_stub}/systems/{system['id']}",
            "title": system["uniqueId"]
        },
        "observedProperties": [{
            "definition": "http://vocab.nerc.ac.uk/collection/P01/current/EWDAZZ01/",
            "label": "WindDirFrom",
            "description": "Direction relative to true north from which the wind is blowing"
        }],
        "phenomenonTime": [
            "2000-08-05T12:36:56.760657+00:00",
            "2099-08-05T12:36:56.760657+00:00"
        ],
        "resultTime": [
            "2002-08-05T12:36:56.760657+00:00",
            "2099-08-05T12:36:56.760657+00:00"
        ],
        "resultType": "measure",
        "live": False,
        "formats": [
            "application/json"
        ],
        "schema": {
            "obsFormat": "application/om+json",
            "resultTimeSchema": {
                "name": "time",
                "type": "Time",
                "definition": "http://www.opengis.net/def/property/OGC/0/SamplingTime",
                "referenceFrame": "http://www.opengis.net/def/trs/BIPM/0/UTC",
                "label": "Sampling Time",
                "uom": {
                    "href": "http://www.opengis.net/def/uom/ISO-8601/0/Gregorian"
                }
            },
            "resultSchema": {
                "name": "temp",
                "type": "Quantity",
                "definition": "http://mmisw.org/ont/cf/parameter/air_temperature",
                "label": "Room Temperature",
                "description": "Ambient air temperature measured inside the room",
                "uom": {
                    "code": "Cel"
                },
                "nilValues": [
                    {
                        "reason": "http://www.opengis.net/def/nil/OGC/0/missing",
                        "value": "NaN"
                    },
                    {
                        "reason": "http://www.opengis.net/def/nil/OGC/0/BelowDetectionRange",
                        "value": "-Infinity"
                    },
                    {
                        "reason": "http://www.opengis.net/def/nil/OGC/0/AboveDetectionRange",
                        "value": "+Infinity"
                    }
                ]
            }
        }
    }


def run():
    # get datastream id
    system = gen_system()
    post("/systems", system, "application/sml+json")

    datastream = gen_datastream(system)
    post(f"/systems/{system['id']}/datastreams", datastream)

    for _ in tqdm(range(num_of_obs_to_insert)):
        post(f"/datastreams/{datastream['id']}/observations", gen_observation(datastream['id']), "application/json")
        # sleep(100 / 1000)


if __name__ == "__main__":
    # import cProfile
    # cProfile.run('run()')
    run()
