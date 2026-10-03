#!/usr/bin/env python3
"""Explicitly initialize an EMPTY owned MySQL evidence database.

This is administrative setup, never imported or called by either MCP server.
Credentials must be supplied through environment variables. No existing schema
is reset; an existing table causes setup to stop before writes.
"""
import hashlib
import json
import os
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[3]


def main():
    url = make_url(os.environ["HW5_FIXTURE_ADMIN_URL"])
    if (url.drivername != "mysql+pymysql" or url.database != "s6102_rel"
            or url.host != "127.0.0.1" or url.port != 3308):
        raise SystemExit("Fixture setup requires the owned localhost:3308/s6102_rel instance.")
    password = os.environ["HW5_FIXTURE_READER_PASSWORD"]
    engine = create_engine(url, hide_parameters=True, connect_args={"charset": "utf8mb4"})
    source = ROOT / "code/web_application/migrations/001_initial.sql"
    sql = source.read_text()
    try:
        with engine.connect() as connection:
            if connection.exec_driver_sql("SHOW TABLES").first():
                raise SystemExit("Refusing fixture setup: database already contains tables.")
            statements = "\n".join(line for line in sql.splitlines()
                                   if not line.lstrip().startswith("--"))
            for statement in statements.split(";"):
                if statement.strip():
                    connection.exec_driver_sql(statement.strip())
            connection.execute(text("INSERT INTO property_managers (id,name) VALUES (:id,:name)"),
                               [{"id": 1, "name": "Campus Homes"},
                                {"id": 2, "name": "Garden Rentals"},
                                {"id": 3, "name": "Empty Portfolio"}])
            titles = ["Sunny Downtown Apartment", "Spacious Garden House",
                      "100% Calm_Studio", "Straße Café", "Café Apartment",
                      "O'Reilly \\ Courtyard", "Unassigned Townhouse"]
            rows = [{"id": i, "title": title,
                     "address": f"{i} Campus Way, San Jose, CA",
                     "email": f"synthetic-owner-{i}@example.com",
                     "description": "Synthetic HW5 evidence listing with a spacious living room.",
                     "kind": "house" if i == 2 else "apartment",
                     "manager": None if i == 7 else (2 if i == 2 else 1)}
                    for i, title in enumerate(titles, 1)]
            connection.execute(text("INSERT INTO rentals "
                "(id,listing_title,property_address,submitter_email,description,property_type,terms_accepted,manager_id) "
                "VALUES (:id,:title,:address,:email,:description,:kind,1,:manager)"), rows)
            connection.commit()
            connection.execute(text("CREATE USER 'hw5_reader'@'%' IDENTIFIED BY :password"),
                               {"password": password})
            # Column-level grants make private contact/auth fields inaccessible.
            connection.execute(text("GRANT SELECT (id,listing_title,property_address,description,property_type,manager_id) ON s6102_rel.rentals TO 'hw5_reader'@'%'"))
            connection.execute(text("GRANT SELECT (id,name) ON s6102_rel.property_managers TO 'hw5_reader'@'%'"))
            connection.commit()
            version = connection.exec_driver_sql("SELECT VERSION()").scalar_one()
        print(json.dumps({"source": "owned MySQL synthetic evidence fixture",
            "host": "127.0.0.1", "port": 3308, "database": "s6102_rel",
            "mysql_version": version, "baseline": str(source.relative_to(ROOT)),
            "baseline_sha256": hashlib.sha256(sql.encode()).hexdigest(),
            "rentals": 7, "managers": 3, "empty_manager_id": 3,
            "runtime_user": "hw5_reader", "runtime_privileges": "public-column SELECT only",
            "data_note": "Synthetic records created explicitly for Part 2; no copied user data."}, indent=2))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
