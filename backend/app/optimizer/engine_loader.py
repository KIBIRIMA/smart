"""
Chargeur de moteur avec cascade fallback v12 → v11 → v10 → v9 → v8.

Le moteur réel (`tournee_optimizer_v*.py`) est importé TEL QUEL, sans modification.
Si aucun n'est présent/importable, on retombe sur `_reference_engine` pour que
l'API reste fonctionnelle de bout en bout.
"""
from __future__ import annotations
import importlib
import logging
from types import ModuleType

logger = logging.getLogger("optimizer.loader")

CASCADE = [
    ("tournee_optimizer_v12", "v12"),
    ("tournee_optimizer_v11", "v11"),
    ("tournee_optimizer_v10", "v10"),
    ("tournee_optimizer_v9", "v9"),
    ("tournee_optimizer_v8", "v8"),
]


def _try_import(modname: str) -> ModuleType | None:
    try:
        # Les moteurs sont déposés dans app/optimizer/ → import relatif au package
        return importlib.import_module(f"app.optimizer.{modname}")
    except Exception as exc:  # import error OR runtime error at import time
        logger.warning("Moteur %s indisponible: %s", modname, exc)
        return None


def load_engine(prefer: str = "v12") -> tuple[ModuleType, str]:
    """Retourne (module_moteur, version). Respecte la préférence puis la cascade."""
    order = CASCADE
    if prefer != "v12":
        order = sorted(CASCADE, key=lambda x: (x[1] != prefer))

    for modname, version in order:
        mod = _try_import(modname)
        if mod is not None and hasattr(mod, "optimize"):
            logger.info("Moteur chargé: %s", version)
            return mod, version

    # Fallback ultime : moteur de référence intégré
    from app.optimizer import _reference_engine
    logger.warning("Aucun moteur tournee_optimizer_v* trouvé — moteur de référence utilisé")
    return _reference_engine, "reference"
