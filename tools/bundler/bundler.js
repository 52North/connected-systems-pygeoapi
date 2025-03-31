// =================================================================
// Copyright (C) 2024 by 52 North Spatial Information Research GmbH
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
// =================================================================

// requires  @hyperjump/json-schema
// npm install @hyperjump/json-schema

import { registerSchema, validate } from "@hyperjump/json-schema/draft-2020-12";
import "@hyperjump/json-schema/draft-07";
import { addMediaTypePlugin } from "@hyperjump/browser";
import { buildSchemaDocument } from "@hyperjump/json-schema/experimental";
import { bundle } from "@hyperjump/json-schema/bundle";
import { readdirSync, readFileSync, writeFile } from "fs";

const baseUrl = "https://connected-systems.n52/"

let datastream_schema = {}

addMediaTypePlugin("application/json", {
    parse: async (response) => {
        //return [JSON.parse(await response.text()),]
        const schema = await response.json()
        return buildSchemaDocument(schema, response.url)
    },
    fileMatcher: (path) => path.endsWith(".json")
});

function parse_directory(name) {
    const directory = "ogcapi-connected-systems/" + name
    readdirSync(directory, { withFileTypes: true })
        .filter((entry) => entry.isFile() && entry.name.endsWith(".json"))
        .forEach((entry) => {
            const file = `${directory}/${entry.name}`;
            let schemaText = readFileSync(file, "utf8")
            const re = /\$ref":\s?"([^"]+)"/g
            let refs = schemaText.matchAll(re)

            // Make all $ref links absolute
            for (const match of refs) {
                let ref = match[1]
                let replacement = ref
                // normalize $ref to use absolute urls
                if (ref.startsWith("#") || ref.startsWith("http")) {
                    // same document - nothing to do
                } else if (ref.startsWith("../common/commonDefs.json#/$defs/")) {
                    // sibling directory
                    if (ref.includes("$defs/Links")) {
                        replacement = "https://connected-systems.n52/api/part1/openapi/schemas/common/links.json"
                    } else {
                        replacement = baseUrl + "common/" + ref.substring(33, 34).toLowerCase() + ref.substring(34) + ".json"
                    }
                } else if (ref.startsWith("../common/sweCommonDefs.json#/$defs/")) {
                    if (ref.includes("AnyComponent")) {
                        replacement = baseUrl + "swecommon/schemas/json/sweCommon.json#/$defs/AnyComponent"
                    } else if (ref.includes("AnyEncoding")) {
                        replacement = baseUrl + "swecommon/schemas/json/encodings.json"
                    } else if (ref.includes("Encoding")) {
                        replacement = baseUrl + "swecommon/schemas/json/encodings.json#/$defs/" + ref.substring(36)
                    } else {
                        replacement = baseUrl + "swecommon/schemas/json/" + ref.substring(36) + ".json"
                    }
                } else if (ref.startsWith(".")) {
                    // higher level
                    replacement = new URL(ref, baseUrl + name + "/").href
                } else if (ref.startsWith("sensormlDefs.json#/$defs/")) {
                    // special case because defs-collector class is optimized out during bundling
                    replacement = baseUrl + "sensorml/schemas/json/" + ref.substring(25) + ".json"
                    // console.log("REPLACING " + ref + " with " + replacement)
                } else if (ref.startsWith("commonDefs.json#/$defs/")) {
                    // special case because defs-collector class is optimized out during bundling
                    if (name.startsWith("sensorml")) {
                        replacement = baseUrl + "sensorml/schemas/json/commonDefs.json#/$defs/" + ref.substring(23)
                    } else {
                        // fix inconsistent naming with upper & lowercase
                        replacement = baseUrl + "common/" + ref.substring(23, 24).toLowerCase() + ref.substring(24) + ".json"
                    }
                } else {
                    // Import by name
                    replacement = baseUrl + name + "/" + ref
                }
                // console.log(`${match[0]}${replacement}`)
                schemaText = schemaText.replace(match[0], `$ref":"${replacement}"`)

            }

            const suite = JSON.parse(schemaText);
            suite["$id"] = baseUrl + name + "/" + entry.name;
            suite["$schema"] ??= "https://json-schema.org/draft/2020-12/schema"

            if (entry.name.includes("DataStream")) {
                datastream_schema = suite
            }
            console.log(`registered schema: ${suite["$id"]}`)

            var cleaned = suite;

            if ('required' in suite) {
                if ('oneOf' in suite || 'allOf' in suite || 'anyOf' in suite) {
                    //console.log("This may lead to problems!!")
                    //console.log(suite)
                }
            }

            if ('oneOf' in suite) {
                cleaned = suite
                cleaned["oneOf"] = suite["oneOf"].map(schema => {
                    return remove_readonly_required(schema)
                })
            } else if ('anyOf' in suite){
                cleaned["anyOf"] = suite["anyOf"].map(schema => {
                    return remove_readonly_required(schema)
                })
            } else if ('allOf' in suite){
                cleaned["allOf"] = suite["allOf"].map(schema => {
                    return remove_readonly_required(schema)
                })
            }
            if ('properties' in suite){
                cleaned = remove_readonly_required(suite)
            } else {
                cleaned = suite
            }

            registerSchema(cleaned)
        });
}

function remove_readonly_required(definition) {
    // Delete readonly properties as they are not valid for Request Validation
    var properties = definition["properties"]

    if (properties && definition["required"]) {

        var not_readonly = Object.entries(properties)
        .filter((key) => {
            return !('readOnly' in key[1])
        }).map((entry) => {
            return entry[0];
        })

        var required;
        if (definition["required"]) {
            required = definition["required"].filter(req => {
                return not_readonly.includes(req);
            })
        }

        // definition["properties"] = (Object.fromEntries(not_readonly.map((t) => [t[0], t[1]])))
        definition["required"] = required
    }
    return definition
}

async function get_bundle(uri, fileName) {
    const bundledSchema = await bundle(uri, {
        // bundleMode: 'full',
        //externalSchemas: ["https://geojson.org/schema/"]
    });

    // fix DataStream not being included due to no usage
    // bundledSchema["definitions"][datastream_schema["$id"]] = datastream_schema

    writeFile("../../connected-systems-api/schemas/" + fileName, JSON.stringify(bundledSchema), err => {
        if (err) {
            console.error(err);
        }
    });
}

parse_directory('common')
parse_directory('sensorml/schemas/json')
parse_directory('swecommon/schemas/json')
parse_directory('api/part1/openapi/schemas/common')
parse_directory('api/part1/openapi/schemas/sensorml')
parse_directory('api/part1/openapi/schemas/geojson')
parse_directory('api/part2/openapi/schemas/common')
parse_directory('api/part2/openapi/schemas/json')

await (get_bundle(baseUrl + 'api/part1/openapi/schemas/sensorml/system.json', "system.sml.schema"))
await (get_bundle(baseUrl + 'api/part1/openapi/schemas/geojson/system.json', "system.geojson.schema"))
await (get_bundle(baseUrl + 'api/part1/openapi/schemas/sensorml/deployment.json', "deployment.sml.schema"))
await (get_bundle(baseUrl + 'api/part1/openapi/schemas/geojson/deployment.json', "deployment.geojson.schema"))
await (get_bundle(baseUrl + 'api/part1/openapi/schemas/sensorml/procedure.json', "procedure.sml.schema"))
await (get_bundle(baseUrl + 'api/part1/openapi/schemas/geojson/procedure.json', "procedure.geojson.schema"))
await (get_bundle(baseUrl + 'api/part1/openapi/schemas/geojson/samplingFeature.json', "samplingFeature.schema"))
await (get_bundle(baseUrl + 'api/part1/openapi/schemas/sensorml/property.json', "property.schema"))
await (get_bundle(baseUrl + 'api/part2/openapi/schemas/json/dataStream.json', "datastream.schema"))
await (get_bundle(baseUrl + 'api/part2/openapi/schemas/json/observation.json', "observation.schema"))