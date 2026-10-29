#!/bin/sh
# User read-only untuk ekstraksi (meniru akun teknis RFC/ODP dengan otorisasi baca saja).
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    create role ${SAP_DB_READER_USER} login password '${SAP_DB_READER_PASSWORD}';
    grant connect on database ${POSTGRES_DB} to ${SAP_DB_READER_USER};
    grant usage on schema sap to ${SAP_DB_READER_USER};
    grant select on all tables in schema sap to ${SAP_DB_READER_USER};
    alter default privileges in schema sap grant select on tables to ${SAP_DB_READER_USER};
EOSQL
