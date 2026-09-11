"""SQLModel data models, one module per entity.

Importing this package imports every submodule, so ``import models`` is all it
takes to register every table on ``SQLModel.metadata`` -- what Alembic and the
test suite rely on. Import a model from the submodule that defines it.
"""

import importlib
import pkgutil

for _module in pkgutil.iter_modules(__path__):
    importlib.import_module(f"{__name__}.{_module.name}")
