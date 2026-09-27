"""Unit tests for PR diff parsing, hunk extraction, and markdown sanitization."""

from unittest.mock import MagicMock

from app.services.github.diff_context_service import DiffContextService
from app.services.github.sanitizer import sanitize_pr_text, wrap_untrusted_content

SAMPLE_DIFF = """diff --git a/app/core/rate_limiter.py b/app/core/rate_limiter.py
index e69de29..b2a8d3e 100644
--- a/app/core/rate_limiter.py
+++ b/app/core/rate_limiter.py
@@ -10,4 +10,6 @@ class RateLimiter:
     def check_limit(self, user_id: str) -> bool:
-        return True
+        # Refactored token calculation
+        tokens = self.get_tokens(user_id)
+        return tokens > 0
diff --git a/app/utils/new_helper.py b/app/utils/new_helper.py
new file mode 100644
--- /dev/null
+++ b/app/utils/new_helper.py
@@ -0,0 +1,5 @@
+def compute_micro_tokens(count: int) -> int:
+    return count * 1000
"""


def test_sanitize_pr_text_strips_scripts():
    malicious = "Fix bug <script>alert('xss')</script> and update logic"
    cleaned = sanitize_pr_text(malicious)
    assert "<script>" not in cleaned
    assert "alert('xss')" not in cleaned
    assert "Fix bug" in cleaned


def test_wrap_untrusted_content():
    content = "rm -rf /"
    wrapped = wrap_untrusted_content("PR_DIFF", content)
    assert "<PR_DIFF_UNTRUSTED_CONTENT>" in wrapped
    assert "</PR_DIFF_UNTRUSTED_CONTENT>" in wrapped
    assert "rm -rf /" in wrapped


def test_parse_changed_files_from_diff():
    mock_db = MagicMock()
    service = DiffContextService(mock_db)

    files = service.parse_changed_files_from_diff(SAMPLE_DIFF)
    assert len(files) == 2

    # First file
    f1 = files[0]
    assert f1["file_path"] == "app/core/rate_limiter.py"
    assert f1["operation"] == "MODIFY"
    assert len(f1["hunks"]) == 1
    assert f1["hunks"][0]["start_line"] == 10

    # Second file (new file)
    f2 = files[1]
    assert f2["file_path"] == "app/utils/new_helper.py"
    assert f2["operation"] == "CREATE"
    assert len(f2["hunks"]) == 1
    assert f2["hunks"][0]["start_line"] == 1



def test_parse_empty_diff():
    mock_db = MagicMock()
    service = DiffContextService(mock_db)

    files = service.parse_changed_files_from_diff("")
    assert files == []
