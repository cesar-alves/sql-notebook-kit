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


@pytest.mark.skipif(not CHROMIUM or not MAGICK, reason="Chromium and ImageMagick required")
def test_dark_editor_controls_use_theme_text(tmp_path):
    css = files("sql_notebook_kit.visualize").joinpath("workspace.css").read_text()
    html = f"""<!doctype html>
<style>
html, body {{ margin: 0; background: #1e1e1e; color-scheme: dark; }}
body {{ padding: 24px; }}
{css}
</style>
<div class="snk-viz-workspace snk-theme-dark" style="width: 560px">
  <div class="snk-editor-panel widget-vbox">
    <div class="widget-inline-hbox snk-editor-control snk-name-control snk-text-control">
      <label class="widget-label" for="name">Name</label><input id="name" value="Revenue">
    </div>
    <div class="widget-inline-hbox snk-editor-control snk-type-control snk-select-control">
      <label class="widget-label" for="type">Type</label>
      <select id="type"><option>Grouped bar chart with a deliberately long label</option></select>
    </div>
    <div class="widget-inline-hbox snk-editor-control snk-field-control snk-select-control">
      <label class="widget-label" for="x">X</label>
      <select id="x"><option>transaction_created_at — datetime</option></select>
    </div>
    <div class="widget-inline-hbox snk-editor-control snk-field-control snk-select-control">
      <label class="widget-label" for="group">Group</label>
      <select id="group"><option>customer_segment_name — categorical</option></select>
    </div>
    <div class="widget-checkbox snk-editor-control snk-option-control snk-checkbox-control">
      <input id="legend" type="checkbox" checked><label for="legend">Show legend</label>
    </div>
    <div class="snk-options-section"><div class="jupyter-widget-Collapse-header">Options</div></div>
  </div>
</div>
"""
    page = tmp_path / "editor.html"
    screenshot = tmp_path / "editor.png"
    profile = tmp_path / "chromium-profile"
    page.write_text(html)

    subprocess.run(
        [
            CHROMIUM,
            "--headless",
            "--no-sandbox",
            "--disable-gpu",
            f"--user-data-dir={profile}",
            "--window-size=640,420",
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

    assert "#F0F0F0" in histogram
    assert "#313131" in histogram
    assert screenshot.stat().st_size > 1_000
