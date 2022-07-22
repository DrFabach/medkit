__all__ = ["context", "ner", "segmentation", "relations"]

import importlib.util
from . import context
from . import ner
from . import segmentation
from . import relations

_spacy_is_available = importlib.util.find_spec("spacy") is not None
if _spacy_is_available:
    # fmt: off
    from . import spacy  # noqa: F401
    __all__.append("spacy")
    # fmt: on

_torch_is_available = importlib.util.find_spec("torch") is not None
_transformers_is_available = importlib.util.find_spec("transformers") is not None
if _transformers_is_available and _torch_is_available:
    # fmt: off
    from .hf_translator import HFTranslator  # noqa: F401
    __all__.append("HFTranslator")
    # fmt: on