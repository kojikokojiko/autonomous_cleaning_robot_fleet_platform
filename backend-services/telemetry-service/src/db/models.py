from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass

# telemetry is a TimescaleDB hypertable - do not create via create_all.
# Queries are executed via raw SQL using sqlalchemy text().
