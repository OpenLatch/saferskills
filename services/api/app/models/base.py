"""SQLAlchemy declarative base for generated models.

Generated model classes under app/models/generated/ inherit from `Base`. The
base carries no shared columns — shared columns (id / created_at / updated_at /
metadata) are added when the real entities arrive.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
