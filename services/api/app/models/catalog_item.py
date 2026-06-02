"""Back-compat re-export of the generated `CatalogItem` ORM model.

`catalog_items` is now schema-driven: the real ORM class is generated from
`schemas/catalog-item.schema.json` into `app/models/generated/catalog_item.py`.
This shim preserves the historical `from app.models.catalog_item import CatalogItem`
import path. Relationships are attached in `app/models/_relationships.py`.
"""

from app.models.generated.catalog_item import CatalogItem

__all__ = ["CatalogItem"]
