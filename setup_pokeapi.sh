#!/bin/sh -xe

prevdir=$(pwd)
BOTDIR=$(dirname "$(realpath -P "$0")"); cd "${BOTDIR}"

if ! [ -d pokeapi ]; then
  git submodule init
fi
git submodule update --recursive
cd pokeapi
# shellcheck disable=SC2039
python3.9 -m pip install -U $(grep -v psycopg2 requirements.txt) psycopg2
newfiles=$(find data/v2/csv -name "*.csv" -newer db.sqlite3 || ls data/v2/csv/*.csv)
make setup
if ! [ -z "$newfiles" ]; then
  python3.9 manage.py shell -c "from data.v2.build import build_all; build_all()" --settings=config.local
fi

cd "$prevdir"