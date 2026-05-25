"""Pydantic base class that all response models inherit from.

Forces `populate_by_name=True` + `by_alias=False` on .model_dump() so API
JSON responses serialise snake_case keys. See `.claude/rules/naming-conventions.md`.
"""

from pydantic import BaseModel, ConfigDict


class OrmBaseModel(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        str_strip_whitespace=True,
    )
