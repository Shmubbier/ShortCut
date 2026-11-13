# Every test process gets a throwaway Codex folder and review log, so no test can ever touch ~/.codex.
import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="shortcut-tests-")
os.environ["CODEX_HOME"] = os.path.join(_tmp, "codex")
os.environ["REVIEW_DATA_DIR"] = _tmp
