"""SQLAlchemy declarative base for generated models.

Generated model classes under app/models/generated/ inherit from `Base`. The
W1 base carries no shared columns — the Track B rewrite adds shared columns
(id / created_at / updated_at / metadata) when the real entities arrive.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
