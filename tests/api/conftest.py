import sys
import types


# Stub heavy ML deps to avoid external downloads during import-time in tests
# 1) transformers.AutoTokenizer
dummy_transformers = types.ModuleType("transformers")

class AutoTokenizer:
    @staticmethod
    def from_pretrained(*args, **kwargs):
        class _T:
            def __init__(self):
                pass
        return _T()

dummy_transformers.AutoTokenizer = AutoTokenizer
class AutoModelForSeq2SeqLM:
    @staticmethod
    def from_pretrained(*args, **kwargs):
        class _M:
            def __init__(self):
                pass
        return _M()
def pipeline(*args, **kwargs):
    class _P:
        def __call__(self, *a, **k):
            return [{"summary_text": "stub"}]
    return _P()
dummy_transformers.AutoModelForSeq2SeqLM = AutoModelForSeq2SeqLM
dummy_transformers.pipeline = pipeline
class _HfLogging:
    @staticmethod
    def set_verbosity_error():
        pass
dummy_transformers.logging = _HfLogging

# 2) sentence_transformers.SentenceTransformer
dummy_sentence_transformers = types.ModuleType("sentence_transformers")

class SentenceTransformer:
    def __init__(self, *args, **kwargs):
        pass
    def encode(self, text, convert_to_numpy=True):
        # Return a fixed-size dummy vector
        import numpy as _np
        return _np.zeros(768) if convert_to_numpy else [0.0] * 768

dummy_sentence_transformers.SentenceTransformer = SentenceTransformer

sys.modules["transformers"] = dummy_transformers
sys.modules["sentence_transformers"] = dummy_sentence_transformers


