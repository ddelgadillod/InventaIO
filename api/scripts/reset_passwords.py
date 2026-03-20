"""
InventAI/o — Reset seed user passwords
Updates app.usuarios with proper bcrypt hashes.
Run once after ETL load (the ETL inserts placeholder hashes).

Usage:
    python scripts/reset_passwords.py

All seed users get password: admin123
"""
import sys
from pathlib import Path

# Add api/ to path so imports work
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, text
from core.config import get_settings
from core.security import hash_password

settings = get_settings()
engine = create_engine(settings.DATABASE_URL)

DEFAULT_PASSWORD = "admin123"

def reset():
    hashed = hash_password(DEFAULT_PASSWORD)
    print(f"Resetting all seed user passwords to '{DEFAULT_PASSWORD}'")
    print(f"Bcrypt hash: {hashed[:30]}...")

    with engine.begin() as conn:
        result = conn.execute(
            text("UPDATE app.usuarios SET password_hash = :h, updated_at = NOW()"),
            {"h": hashed},
        )
        print(f"Updated {result.rowcount} users")

        # Verify
        rows = conn.execute(
            text("SELECT email, nombre, rol FROM app.usuarios ORDER BY id")
        ).fetchall()

        print("\nUsers ready for login:")
        for email, nombre, rol in rows:
            print(f"  {email:<35} {nombre:<20} {rol}")
        print(f"\nPassword for all: {DEFAULT_PASSWORD}")


if __name__ == "__main__":
    reset()
