#!/bin/bash

# Use the local virtualenv without needing it activated in the shell first.
# Windows venvs put executables in Scripts/, everything else in bin/.
VENV="$(dirname "$0")/.venv"
for dir in "${VENV}/bin" "${VENV}/Scripts"; do
    if [[ -d ${dir} ]]; then
        PATH="${dir}:${PATH}"
        export PATH
    fi
done


case $1 in
    server)

    flask --app app run --debug --port "${PORT:-8000}"

    ;;

    install)

    python -m pip install -r requirements-dev.txt

    ;;

    lint)

    ruff check . && ruff format --check .

    ;;

    *)
        echo "Option not found, use one of these: server, install, lint"
        exit 1
    ;;
esac
