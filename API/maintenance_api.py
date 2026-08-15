import sqlite3
from pathlib import Path

from fastapi import FastAPI, HTTPException


app = FastAPI(title="Asset Maintenance API")


DATABASE_PATH = (
    Path(__file__).parent.parent
    / "Database"
    / "Maintenance.db"
)


def get_connection():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


@app.get("/assets")
def get_assets():
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            asset_id,
            asset_name,
            asset_type,
            serial_number,
            condition,
            status,
            updated_at
        FROM assets
    """)

    assets = [dict(row) for row in cursor.fetchall()]

    connection.close()

    return assets


@app.get("/assets/{asset_id}")
def get_asset(asset_id: int):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            asset_id,
            asset_name,
            asset_type,
            serial_number,
            condition,
            status,
            updated_at
        FROM assets
        WHERE asset_id = ?
    """, (asset_id,))

    asset = cursor.fetchone()

    if asset is None:
        connection.close()

        raise HTTPException(
            status_code=404,
            detail=f"Asset {asset_id} not found"
        )

    cursor.execute("""
        SELECT
            maintenance_id,
            maintenance_type,
            description,
            service_date,
            next_service_date,
            technician,
            created_at
        FROM maintenance_records
        WHERE asset_id = ?
        ORDER BY service_date DESC
    """, (asset_id,))

    maintenance_records = [
        dict(row) for row in cursor.fetchall()
    ]

    connection.close()

    result = dict(asset)

    result["maintenance_records"] = maintenance_records

    return result