"""Ingestion source adapters.

Each module registers its adapter class in ADAPTER_REGISTRY via
`@register_adapter("<source_name>")`. This package __init__ imports every
adapter module so the registry is fully populated whenever
`app.ingestion.sources` is imported (e.g. by tasks.py).
"""

# Side-effect imports: register each adapter class in ADAPTER_REGISTRY.
from . import claudeskills_info as _csi  # noqa: F401  # pyright: ignore[reportUnusedImport]
from . import clawhub as _clawhub  # noqa: F401  # pyright: ignore[reportUnusedImport]
from . import github_skills_webhook as _ws  # noqa: F401  # pyright: ignore[reportUnusedImport]
from . import github_topics as _gt  # noqa: F401  # pyright: ignore[reportUnusedImport]
from . import glama as _glama  # noqa: F401  # pyright: ignore[reportUnusedImport]
from . import mcp_registry as _mr  # noqa: F401  # pyright: ignore[reportUnusedImport]
from . import mcp_so as _mcp_so  # noqa: F401  # pyright: ignore[reportUnusedImport]
from . import npm as _npm  # noqa: F401  # pyright: ignore[reportUnusedImport]
from . import pulsemcp as _pulsemcp  # noqa: F401  # pyright: ignore[reportUnusedImport]
from . import pypi as _pypi  # noqa: F401  # pyright: ignore[reportUnusedImport]
from . import skillhub_club as _skillhub  # noqa: F401  # pyright: ignore[reportUnusedImport]
from . import skills_sh as _skills_sh  # noqa: F401  # pyright: ignore[reportUnusedImport]
from . import skillsmp as _skillsmp  # noqa: F401  # pyright: ignore[reportUnusedImport]
from . import smithery as _smithery  # noqa: F401  # pyright: ignore[reportUnusedImport]
