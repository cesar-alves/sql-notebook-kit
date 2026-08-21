import re
import shutil
import subprocess
from importlib.resources import files

import pytest

CHROMIUM = shutil.which("chromium") or shutil.which("chromium-browser")
MAGICK = shutil.which("magick")


@pytest.mark.skipif(not CHROMIUM or not MAGICK, reason="Chromium and ImageMagick required")
def test_dark_table_has_no_white_outer_effect(tmp_path):
    css = files("sql_notebook_kit.visualize").joinpath("workspace.css").read_text()
    html = f"""<!doctype html>
<style>
html, body {{ margin: 0; background: #232323; color-scheme: dark; }}
body {{ padding: 24px; }}
{css}
</style>
<div class="snk-viz-workspace" style="--snk-bg:#232323;--snk-surface:#1f2021;
  --snk-surface-muted:#232425;--snk-text:#bfbfbf;--snk-border:#343536;
  --snk-focus:#3994bc;--snk-selection-bg:#363636">
  <div class="widget-vbox snk-active-output">
    <div class="widget-html">
      <div class="widget-html-content">
        <div class="snk-table-wrap snk-copy-table">
          <table class="snk-result-table" role="grid">
            <thead><tr>
              <th tabindex="0" data-snk-row="0" data-snk-column="0">database_name</th>
              <th tabindex="-1" data-snk-row="0" data-snk-column="1">duckdb_version</th>
            </tr></thead>
            <tbody><tr>
              <td tabindex="-1" data-snk-row="1" data-snk-column="0">warehouse</td>
              <td tabindex="-1" data-snk-row="1" data-snk-column="1">v1.5.5</td>
            </tr></tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</div>
"""
    assert "jp-OutputArea" not in html
    page = tmp_path / "table.html"
    screenshot = tmp_path / "table.png"
    profile = tmp_path / "chromium-profile"
    page.write_text(html)

    subprocess.run(
        [
            CHROMIUM,
            "--headless",
            "--no-sandbox",
            "--disable-gpu",
            f"--user-data-dir={profile}",
            "--window-size=900,240",
            f"--screenshot={screenshot}",
            page.as_uri(),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    histogram = subprocess.run(
        [MAGICK, screenshot, "-format", "%c", "histogram:info:-"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.upper()

    assert not re.search(r"#(?:FFFFFF|FFFFFFFF)(?:\s|$)", histogram)
    assert "#343536" in histogram
