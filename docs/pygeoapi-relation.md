# Relation to upstream pygeoapi

## Summary

This repository started from the idea of integrating OGC API Connected Systems closely with pygeoapi. The current
implementation has diverged from that original goal.

Today, the project should be described as:

- a standalone Connected Systems API service
- implemented in this repository
- reusing pygeoapi internals and extension points where that is practical
- pinned to a specific 52North pygeoapi revision

It should **not** currently be described as a vanilla pygeoapi deployment that can be enabled purely through
configuration.

## Evidence in the repository

The current relationship to pygeoapi is visible in a few key files:

| File | What it shows |
| --- | --- |
| `connected-systems-api/app.py` | The service runs its own Quart application, CORS/auth setup, metrics, blueprint registration, and provider lifecycle hooks. |
| `connected-systems-api/api.py` | The service registers Connected Systems providers into `pygeoapi.plugin.PLUGINS`, loads config/OpenAPI through pygeoapi, and creates the local `CSAPI` integration layer. |
| `connected-systems-api/routes/*.py` | Route families are owned locally, then either handled by local Connected Systems code or delegated to upstream pygeoapi route handlers. |
| `connected-systems-api/default-config.yml` | Both standard `resources` and Connected Systems `dynamic-resources` are configured side by side. |
| `pyproject.toml` | pygeoapi is a direct dependency and is pinned to a specific 52North fork revision. |

## How the integration actually works today

### 1. Application bootstrap is local, not vanilla pygeoapi

The service is started through `connected-systems-api/app.py`, which creates a custom Quart application and registers
local blueprints. This is a different runtime shape from running pygeoapi's stock application entrypoint.

Implications:

- request handling is adapted for Quart through `CustomQuart` and `AsyncAPIRequest`
- authentication, metrics, lifecycle hooks, and provider connection management are handled locally
- the service owns its own route registration and boot sequence
- the service does not run pygeoapi's stock Flask application as its primary runtime

### 2. Configuration and OpenAPI loading still come from pygeoapi

`connected-systems-api/api.py` uses:

- `pygeoapi.config.get_config`
- `pygeoapi.openapi.load_openapi_document`
- `pygeoapi.API`

The repository therefore still depends on pygeoapi's configuration model, OpenAPI loading, and core API object.
If `PYGEOAPI_CONFIG` and `PYGEOAPI_OPENAPI` are not provided, the code sets defaults to the bundled config and
OpenAPI files in this repository.

At import time, `connected-systems-api/api.py` also:

- registers local Connected Systems providers into `pygeoapi.plugin.PLUGINS`
- creates `csapi_` for Connected Systems behavior
- creates a pygeoapi `API` instance for reused upstream functionality

### 3. Provider integration uses pygeoapi's plugin registry

The repository registers custom providers by extending `pygeoapi.plugin.PLUGINS` at runtime. The Connected Systems
backends are then loaded through pygeoapi's plugin mechanism from `dynamic-resources` entries in the config.

This is the most "vanilla pygeoapi" part of the current architecture: provider loading is still plugin-based and
configuration-driven.

### 4. Upstream pygeoapi route handlers are reused selectively

Several capabilities are delegated to upstream pygeoapi handlers:

- Processes
- STAC
- EDR
- Coverages
- tiles and queryables under Collections
- the pygeoapi-defined portion of `/collections` and `/collections/{id}/items`

The route modules adapt Quart requests into `AsyncAPIRequest` objects and call upstream `pygeoapi.api.*` handlers.
Connected Systems-specific resources and behavior are implemented locally in `CSAPI`, `CSMeta`, the custom routes, and
the Connected Systems providers.

An important nuance is that the delegated route modules currently import `api_` and `CONFIG` from
`pygeoapi.flask_app`, even though the runtime itself is a custom Quart application. That means the service is not just
reusing public pygeoapi concepts; it is also coupled to upstream module-level application state.

### 5. Collections are merged from two models

The service combines:

- regular pygeoapi `resources`
- Connected Systems `dynamic-resources`

This lets the landing page and `/collections` expose standard pygeoapi resources next to Connected Systems resources,
but it also means the service is doing local orchestration work that vanilla pygeoapi does not perform on its own.

## Current maintenance implications

The current architecture has a few practical consequences:

- upgrades are sensitive to internal pygeoapi API changes, not just documented extension points
- request/response behavior is split across local Quart code and reused upstream handlers
- compatibility testing needs to cover both normal pygeoapi resources and Connected Systems `dynamic-resources`
- contributor expectations should be set around "service plus adapter layer", not "config-only extension"

## What "vanilla pygeoapi" would mean here

For this repository, "vanilla pygeoapi" would mean the following:

- the stock pygeoapi app is the primary runtime
- Connected Systems support is added mostly through documented plugin and configuration hooks
- route registration, request adaptation, and service lifecycle stay inside upstream pygeoapi
- local code mainly contributes providers, templates, and narrowly scoped extension points

That is not the current state of the repository.

## Why the current description needed correction

Historically, the name and top-level wording imply a tighter relationship to pygeoapi than the code now reflects.
That mismatch creates confusion in at least three places:

- contributors may expect a drop-in pygeoapi extension and instead find a custom service
- reviewers may underestimate the amount of local application logic and maintenance burden
- future maintainers may not realize that upstream compatibility depends on internal pygeoapi APIs staying stable

The documentation should therefore be explicit that pygeoapi is currently a dependency and integration layer, not the
whole product runtime.

## Future strategy

The project should choose between two paths and document that choice explicitly. Based on the current codebase, the
default planning assumption should be **Path B** unless the team intentionally invests in upstream convergence work.

### Path A: converge back toward vanilla pygeoapi

Recommended only if upstream compatibility is a strategic goal.

Short-term steps:

- keep documenting which pygeoapi internals are used today
- reduce direct coupling to private or runtime-specific assumptions where possible
- move more Connected Systems behavior behind provider, plugin, or configuration boundaries

Medium-term steps:

- identify missing upstream extension points needed for Connected Systems support
- contribute or maintain those hooks in the 52North pygeoapi fork first, then upstream where possible
- shrink the custom app layer until the stock pygeoapi runtime can host most behavior

Success criterion:

- the repository becomes mostly an extension package and configuration profile rather than a standalone service

### Path B: acknowledge the project as a standalone service using pygeoapi as a dependency

Recommended if the custom routing, async behavior, lifecycle management, and Connected Systems domain model remain
substantial.

Short-term steps:

- document the current architecture honestly
- treat pygeoapi as an internal platform dependency with a pinned version
- make compatibility expectations explicit in release notes and contributor docs

Medium-term steps:

- define a stable internal boundary between local Connected Systems code and reused pygeoapi functionality
- isolate the pygeoapi-specific adapter layer so upgrades are easier to reason about
- only upstream pieces that are clearly reusable outside this product

Success criterion:

- the repository is maintained as its own service, with pygeoapi framed as a library dependency rather than the host

### Recommended near-term strategy

For the repository in its current state, contributors should optimize for Path B:

- document pygeoapi usage as an adapter boundary, not as the primary product runtime
- keep the pygeoapi dependency pinned until the upgrade surface is better isolated
- reduce accidental coupling where possible, especially module-level assumptions and upstream private behavior
- revisit Path A only if there is a clear product decision to make vanilla-pygeoapi hosting a supported goal

## Recommended naming strategy

Short term:

- keep the repository name for continuity in the short term
- update product descriptions to say "standalone service built on top of pygeoapi internals" or "using pygeoapi as a dependency"
- avoid promising "seamless vanilla pygeoapi integration" in contributor docs, release notes, and package metadata

If Path B remains the long-term direction, a future rename would better reflect reality. Candidate names include:

- `connected-systems-api`
- `52n-connected-systems-api`
- `ogcapi-connected-systems-service`

These names describe the product without implying that the runtime is a near-vanilla pygeoapi instance.

For this issue, that means documentation should change now, while a repository rename can remain a separate
intentional follow-up decision.

## Recommended wording for future docs

Use wording like this:

> 52North Connected Systems API is a standalone service that reuses pygeoapi internals, configuration loading, and
> plugin mechanisms where appropriate. It is not currently a vanilla pygeoapi deployment.

Avoid wording like this:

> Connected Systems API is seamlessly integrated with vanilla pygeoapi.
