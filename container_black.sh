#!/bin/bash

# run most recent black from container (requires docker)
# usage e.g. "./container_black.sh ."
# when updating here please also update the version in .github/workflows/black.yml
docker run --rm --volume $(pwd):/src --workdir /src pyfound/black:22.10.0 black "$@"

