import sqlite3
from pathlib import Path

from fastapi import FastAPI, HTTPException


app = FastAPI(title="Asset Inventory API")


DATABASE_PATH = (
    Path(__file__).parent.parent
    / "Database"
    / "Inventory.db"
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
            quantity,
            availability,
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
            quantity,
            availability,
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
            movement_id,
            movement_type,
            quantity,
            from_location,
            to_location,
            movement_time
        FROM inventory_movements
        WHERE asset_id = ?
        ORDER BY movement_time DESC
    """, (asset_id,))

    movements = [
        dict(row) for row in cursor.fetchall()
    ]

    connection.close()

    result = dict(asset)

    result["inventory_movements"] = movements

    return result