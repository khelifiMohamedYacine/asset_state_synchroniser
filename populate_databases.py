import sqlite3
from pathlib import Path


DATABASE_DIR = Path(__file__).parent / "Database"


def populate_location_database():
    db_path = DATABASE_DIR / "location.db"

    connection = sqlite3.connect(db_path)
    cursor = connection.cursor()

    assets = [
        (1001, "Site Alpha",   51.5001, -0.1201, "operational",    "2026-08-12 10:00:00", "2026-08-12 10:00:00"),
        (1002, "Warehouse A",  51.5012, -0.1212, "operational",    "2026-08-12 10:05:00", "2026-08-12 10:05:00"),
        (1003, "Site Beta",    51.5023, -0.1223, "out_of_service", "2026-08-12 10:10:00", "2026-08-12 10:10:00"),
        (1004, "Depot C",      51.5034, -0.1234, "in_transit",     "2026-08-12 10:15:00", "2026-08-12 10:15:00"),
        (1005, "Site Gamma",   51.5045, -0.1245, "operational",    "2026-08-12 10:20:00", "2026-08-12 10:20:00"),
    ]

    cursor.executemany("""
        INSERT INTO asset_locations
        (asset_id, location, latitude, longitude, status, last_seen, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, assets)

    connection.commit()
    connection.close()

    print("Location database populated.")


def populate_maintenance_database():
    db_path = DATABASE_DIR / "maintenance.db"

    connection = sqlite3.connect(db_path)
    cursor = connection.cursor()

    assets = [
        (1001, "Generator G1", "Generator", "GEN-001", "good", "operational",    "2026-08-12 11:00:00"),
        (1002, "Forklift F2",  "Forklift",  "FL-002",  "fair", "under_repair",   "2026-08-12 11:05:00"),
        (1003, "Pump P3",      "Pump",      "PMP-003", "poor", "out_of_service", "2026-08-12 11:10:00"),
        (1004, "Truck T4",     "Truck",     "TRK-004", "good", "operational",    "2026-08-12 11:15:00"),
        (1005, "Generator G5", "Generator", "GEN-005", "good", "operational",    "2026-08-12 11:20:00"),
    ]

    cursor.executemany("""
        INSERT INTO assets
        (asset_id, asset_name, asset_type, serial_number, condition, status, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, assets)

    maintenance_records = [
        (1001, "inspection",         "Routine inspection completed. No defects identified.",
         "2026-07-30", "2026-10-30", "John Smith",   "2026-07-30 14:00:00"),
        (1002, "corrective_repair",  "Hydraulic system requires corrective repair.",
         "2026-08-01", "2026-11-01", "Sarah Jones",  "2026-08-01 09:30:00"),
        (1003, "inspection",         "Pump showing significant mechanical wear and is not fit for operation.",
         "2026-06-20", "2026-09-20", "Mike Brown",   "2026-06-20 15:00:00"),
        (1004, "preventive_service", "Scheduled preventive service completed successfully.",
         "2026-07-10", "2026-10-10", "David Wilson", "2026-07-10 10:00:00"),
        (1005, "inspection",         "Generator operating within normal parameters.",
         "2026-07-28", "2026-10-28", "Emma Davis",   "2026-07-28 11:00:00"),
    ]

    cursor.executemany("""
        INSERT INTO maintenance_records
        (asset_id, maintenance_type, description, service_date, next_service_date, technician, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, maintenance_records)

    connection.commit()
    connection.close()

    print("Maintenance database populated.")


def populate_inventory_database():
    db_path = DATABASE_DIR / "inventory.db"

    connection = sqlite3.connect(db_path)
    cursor = connection.cursor()

    assets = [
        (1001, "Generator G1", "Generator", "GEN-001", 1, "available",           "2026-08-12 12:00:00"),
        (1002, "Forklift F2",  "Forklift",  "FL-002",  1, "available",           "2026-08-12 12:05:00"),
        (1003, "Pump P3",      "Pump",      "PMP-003", 2, "held_for_inspection", "2026-08-12 12:10:00"),
        (1004, "Truck T4",     "Truck",     "TRK-004", 1, "available",           "2026-08-12 12:15:00"),
        (1005, "Generator G5", "Generator", "GEN-005", 1, "available",           "2026-08-12 12:20:00"),
    ]

    cursor.executemany("""
        INSERT INTO assets
        (asset_id, asset_name, asset_type, serial_number, quantity, availability, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, assets)

    inventory_movements = [
        (1001, "IN",       1, None,          "Site Alpha",   "2026-07-01 09:00:00"),
        (1002, "TRANSFER", 1, "Depot C",     "Warehouse A",  "2026-08-05 10:00:00"),
        (1003, "IN",       2, None,          "Site Beta",    "2026-06-15 12:00:00"),
        (1004, "TRANSFER", 1, "Warehouse B", "Depot C",      "2026-08-08 14:00:00"),
        (1005, "IN",       1, None,          "Site Gamma",   "2026-07-05 08:30:00"),
    ]

    cursor.executemany("""
        INSERT INTO inventory_movements
        (asset_id, movement_type, quantity, from_location, to_location, movement_time)
        VALUES (?, ?, ?, ?, ?, ?)
    """, inventory_movements)

    connection.commit()
    connection.close()

    print("Inventory database populated.")


if __name__ == "__main__":
    populate_location_database()
    populate_maintenance_database()
    populate_inventory_database()

    print("\nAll databases populated successfully!")
