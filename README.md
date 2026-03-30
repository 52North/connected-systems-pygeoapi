# connected-systems-pygeoapi

Prototype implementation of OGC API Connected Systems that currently runs as a standalone Quart service while
reusing selected pygeoapi internals.

> Current status: this repository does **not** integrate with vanilla pygeoapi as a purely config-driven deployment.
> It runs a custom Quart application that reuses selected pygeoapi APIs, configuration loading, templating, and plugin
> infrastructure while implementing Connected Systems behavior in this codebase.

For the detailed architecture and upstream relation, see [docs/pygeoapi-relation.md](docs/pygeoapi-relation.md).

## What this repository is today

- A standalone Connected Systems API service with its own application entrypoint in `connected-systems-api/app.py`.
- A pygeoapi-based integration layer that still reuses upstream request handling, OpenAPI loading, templating helpers,
  route handlers for selected OGC APIs, and the provider/plugin registry.
- A prototype that is currently pinned to a specific 52North pygeoapi revision via `pyproject.toml`.

## Integration with pygeoapi

The current integration model is hybrid:

- `connected-systems-api/api.py` registers custom Connected Systems provider plugins in the pygeoapi plugin registry,
  loads configuration and OpenAPI documents through pygeoapi, and instantiates the local `CSAPI` object plus a
  pygeoapi `API` object.
- `connected-systems-api/app.py` starts a custom Quart app and registers local blueprints for Connected Systems,
  collections, STAC, EDR, coverages, and processes.
- Several routes adapt Quart requests into `AsyncAPIRequest` objects and delegate directly to upstream pygeoapi route
  handlers, especially for Processes, STAC, EDR, Coverages, tiles, and parts of Collections.
- Connected Systems resources themselves are implemented locally and plugged in via `dynamic-resources`.

This means the project should currently be understood as "a standalone service that depends on pygeoapi internals",
not as "vanilla pygeoapi plus configuration".

## Current direction

The working assumption for contributors should be:

- treat this repository as a standalone Connected Systems service first
- treat pygeoapi as a pinned platform dependency and adapter layer
- only pursue convergence back toward vanilla pygeoapi if that becomes an explicit product goal

The detailed rationale and future-path discussion live in [docs/pygeoapi-relation.md](docs/pygeoapi-relation.md).

## Running the service

### Development dependencies

The repository uses `uv` for dependency management.

```commandline
uv sync
```

### Start supporting services

`docker-compose-dev.yml` starts the development backing services such as Elasticsearch, TimescaleDB, Kibana, and
pgAdmin. It does not start the application itself by default.

```commandline
docker compose -f docker-compose-dev.yml up -d
```

### Start the application

```commandline
uv run hypercorn -c hypercorn.conf.py connected-systems-api/app:APP
```

By default the application reads:

- `PYGEOAPI_CONFIG` for the pygeoapi-compatible service configuration
- `PYGEOAPI_OPENAPI` for the OpenAPI document
- `CSA_*` environment variables for Connected Systems-specific overrides

If these are not set, `connected-systems-api/api.py` falls back to the repository's bundled defaults.

## Example data

You can insert example data into a running instance by using [tools/simulator/simulator.py](tools/simulator/simulator.py).
Install the simulator's dependencies from [tools/simulator/requirements.txt](tools/simulator/requirements.txt) in a
separate environment if needed.

## Documentation notes

The current repository name reflects the historical origin of the project. The documentation in
[docs/pygeoapi-relation.md](docs/pygeoapi-relation.md) explains why that name is now only partially accurate,
recommends current wording for docs and releases, and captures the longer-term naming strategy if the project remains
a standalone service.

## License

The software is licensed under the Apache License 2.0. See [LICENSE](LICENSE) for details.
