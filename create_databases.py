import sqlite3
from pathlib import Path


DATABASE_DIR = Path(__file__).parent / "Database"
DATABASE_DIR.mkdir(exist_ok=True)


def create_location_database():
    db_path = DATABASE_DIR / "Location.db"

    connection = sqlite3.connect(db_path)
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS asset_locations (
            asset_id INTEGER PRIMARY KEY,
            location VARCHAR(100) NOT NULL,
            latitude REAL,
            longitude REAL,
            status VARCHAR(30),
            last_seen DATETIME,
            updated_at DATETIME NOT NULL
        )
    """)

    connection.commit()
    connection.close()

    print("Location database created.")


def create_maintenance_database():
    db_path = DATABASE_DIR / "Maintenance.db"

    connection = sqlite3.connect(db_path)
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS assets (
            asset_id INTEGER PRIMARY KEY,
            asset_name VARCHAR(100) NOT NULL,
            asset_type VARCHAR(50) NOT NULL,
            serial_number VARCHAR(100) UNIQUE NOT NULL,
            condition VARCHAR(30),
            status VARCHAR(30),
            updated_at DATETIME NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS maintenance_records (
            maintenance_id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_id INTEGER NOT NULL,
            maintenance_type VARCHAR(50) NOT NULL,
            description TEXT,
            service_date DATE,
            next_service_date DATE,
            technician VARCHAR(100),
            created_at DATETIME NOT NULL,

            FOREIGN KEY (asset_id)
                REFERENCES assets(asset_id)
        )
    """)

    connection.commit()
    connection.close()

    print("Maintenance database created.")


def create_inventory_database():
    db_path = DATABASE_DIR / "Inventory.db"

    connection = sqlite3.connect(db_path)
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS assets (
            asset_id INTEGER PRIMARY KEY,
            asset_name VARCHAR(100) NOT NULL,
            asset_type VARCHAR(50) NOT NULL,
            serial_number VARCHAR(100) UNIQUE NOT NULL,
            quantity INTEGER NOT NULL,
            availability VARCHAR(30),
            updated_at DATETIME NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventory_movements (
            movement_id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_id INTEGER NOT NULL,
            movement_type VARCHAR(30) NOT NULL,
            quantity INTEGER NOT NULL,
            from_location VARCHAR(100),
            to_location VARCHAR(100),
            movement_time DATETIME NOT NULL,

            FOREIGN KEY (asset_id)
                REFERENCES assets(asset_id)
        )
    """)

    connection.commit()
    connection.close()

    print("Inventory database created.")


if __name__ == "__main__":
    create_location_database()
    create_maintenance_database()
    create_inventory_database()

    print("\nAll databases created successfully!")