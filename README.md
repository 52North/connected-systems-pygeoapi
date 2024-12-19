# connected-systems-pygeoapi

Proof of Concept of the OGC Connected Systems API based on pygeoapi

## Installation

### Docker

Example Setups for each backend are provided in the respective subfolder in the `./docker/` subdirectory.

Build appropriate docker container (choose either target)

```commandline
docker compose build connected-systems-api
```

Note: When building manually make sure to specify the `target` as either `hybrid` or `toardb`.

```commandline
docker build --target=<hybrid|toardb> .
```

### Local/Development Installation

The specific installation instructions depend on the actual backend to be used, as each backend may require additional dependencies.

Installation of requirements:

```commandline
pip install -r requirements.txt
pip install --no-deps -r requirements_nodeps.txt

[if toardb backend is used]
pip install -r requirements_toardb_csa.txt

[if elasticsearch backend is used]
pip install -r requirements_elasticsearch_csa.txt
```

If additional providers are used, e.g. for serving a `STAC` interface in parallel to Connected-Systems, additional
dependencies may be necessary depending on the used underlying provider.

The application can then be started from the root directory via

```commandline
python3 connected-systems-api/app.py 
```

### devcontainer

This repository contains [devcontainer](https://code.visualstudio.com/docs/devcontainers/containers) configurations.
Before using them, the `docker/examples/hybrid-csa/.env-sample` or any other working `.env` MUST be provided by copying it to the `.devcontainer/` folder.

Remember to rebuild the containers, if any other example set-up from `docker/examples` was executed beforehand.

### Example Data

You can insert example data into your running instance (`url_stub`) by using the [simulator](./tools/simulator/simulator.py).
Ensure to set-up your python environment accordingly and install the [required dependencies](./tools/simulator/requirements.txt) in your simulator env.
You can limit the amount of observations (`num_of_obs_to_insert`) being inserted in the `simlutor.py`

## Usage

The API is accessible at `<host>:5000` and provides a HTML landing page for easy navigation.

## License

The software is licensed under the `Apache 2.0 License`. See [LICENSE.md](LICENSE.md) for details.

## Contributors
