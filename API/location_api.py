import sqlite3
from pathlib import Path

from fastapi import FastAPI, HTTPException


app = FastAPI(title="Asset Location API")


DATABASE_PATH = (
    Path(__file__).parent.parent
    / "Database"
    / "Location.db"
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
            location,
            latitude,
            longitude,
            status,
            last_seen,
            updated_at
        FROM asset_locations
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
            location,
            latitude,
            longitude,
            status,
            last_seen,
            updated_at
        FROM asset_locations
        WHERE asset_id = ?
    """, (asset_id,))

    asset = cursor.fetchone()

    connection.close()

    if asset is None:
        raise HTTPException(
            status_code=404,
            detail=f"Asset {asset_id} not found"
        )

    return dict(asset)