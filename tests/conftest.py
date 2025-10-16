from __future__ import annotations

import sys
import types
from pathlib import Path

if "litellm" not in sys.modules:
    utils_stub = types.SimpleNamespace(
        supports_vision=lambda model: True,
        supports_pdf_input=lambda model: True,
    )

    def _not_configured(*args, **kwargs):
        raise RuntimeError("litellm stub invoked during tests")

    litellm_stub = types.ModuleType("litellm")
    setattr(litellm_stub, "utils", utils_stub)
    setattr(litellm_stub, "completion", _not_configured)
    setattr(litellm_stub, "embedding", _not_configured)
    sys.modules["litellm"] = litellm_stub

if "sklearn" not in sys.modules:
    import numpy as _np

    class _StubKMeans:
        def __init__(self, n_clusters: int, random_state: int, n_init):
            self.n_clusters = n_clusters
            self.random_state = random_state
            self.n_init = n_init

        def fit_predict(self, data: _np.ndarray) -> _np.ndarray:
            if len(data) == 0:
                return _np.array([], dtype=int)
            mean = data[:, 0].mean()
            labels = (data[:, 0] > mean).astype(int)
            return labels

    sklearn_module = types.ModuleType("sklearn")
    cluster_module = types.ModuleType("sklearn.cluster")
    setattr(cluster_module, "KMeans", _StubKMeans)
    setattr(sklearn_module, "cluster", cluster_module)
    sys.modules["sklearn"] = sklearn_module
    sys.modules["sklearn.cluster"] = cluster_module

SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))
