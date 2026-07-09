"""Pin the test suite to offline/mock inference.

The API app calls load_dotenv() at import, which would otherwise pull a real hosted VLM key from
.env into os.environ and make agents hit the network during tests. pytest imports conftest before
any test module (and before the app), and load_dotenv(override=False) won't clobber these, so the
suite stays deterministic and offline.
"""
import os
import tempfile

os.environ["INFERENCE_MODE"] = "mock"
os.environ["MODEL_PROFILE"] = "mock"
os.environ["HOSTED_VLM_BASE_URL"] = ""
os.environ["HOSTED_VLM_API_KEY"] = ""
# Isolate persistence so tests never read/write the real data/store.json.
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="processiq-test-")
