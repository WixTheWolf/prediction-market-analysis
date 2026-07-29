import re
import shutil
import subprocess
from pathlib import Path


def test_dashboard_references_all_published_data_files() -> None:
    html = Path("dashboard/index.html").read_text(encoding="utf-8")
    for filename in (
        "latest-scan.json",
        "opportunities.json",
        "run-metadata.json",
        "evidence-metadata.json",
        "history.json",
    ):
        assert filename in html
    for view in ("plays", "radar", "markets", "portfolio", "performance", "system"):
        assert f'data-view="{view}"' in html


def test_dashboard_javascript_has_valid_syntax(tmp_path: Path) -> None:
    node = shutil.which("node")
    if node is None:
        return
    html = Path("dashboard/index.html").read_text(encoding="utf-8")
    matches = re.findall(r"<script>([\s\S]*?)</script>", html)
    assert len(matches) == 1
    script = tmp_path / "dashboard.js"
    script.write_text(matches[0], encoding="utf-8")
    result = subprocess.run([node, "--check", str(script)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
