from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import nbformat
import pytest

ROOT = Path(__file__).parents[1]

pytestmark = [
    pytest.mark.browser,
    pytest.mark.skipif(
        os.environ.get("SQL_NOTEBOOK_KIT_BROWSER_SMOKE") != "1",
        reason="set SQL_NOTEBOOK_KIT_BROWSER_SMOKE=1 to run the full JupyterLab browser smoke",
    ),
]


def _available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _wait_for_server(url: str, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            raise AssertionError(f"JupyterLab stopped during startup\n{stdout}\n{stderr}")
        try:
            with urllib.request.urlopen(url, timeout=1) as response:  # noqa: S310
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.25)
    raise AssertionError("JupyterLab did not become ready within 45 seconds")


@contextmanager
def _jupyter_lab(root: Path) -> Iterator[str]:
    data_dir = root / ".jupyter-data"
    extension = (
        data_dir / "labextensions" / "@sql-notebook-kit" / "jupyterlab"
    )
    shutil.copytree(ROOT / "sql_notebook_kit" / "labextension", extension)
    environment = dict(os.environ)
    existing_data = environment.get("JUPYTER_PATH")
    environment["JUPYTER_PATH"] = (
        str(data_dir)
        if not existing_data
        else f"{data_dir}{os.pathsep}{existing_data}"
    )
    port = _available_port()
    url = f"http://127.0.0.1:{port}/lab/tree/browser-smoke.ipynb"
    command = [
        sys.executable,
        "-m",
        "jupyterlab",
        "--no-browser",
        f"--ServerApp.root_dir={root}",
        f"--ServerApp.port={port}",
        "--ServerApp.port_retries=0",
        "--IdentityProvider.token=",
    ]
    process = subprocess.Popen(
        command,
        cwd=root,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    failure: BaseException | None = None
    try:
        _wait_for_server(url, process)
        yield url
    except BaseException as exc:
        failure = exc
        raise
    finally:
        process.terminate()
        try:
            stdout, stderr = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate(timeout=5)
        if failure is not None:
            print("JupyterLab stdout:\n" + stdout, file=sys.stderr)
            print("JupyterLab stderr:\n" + stderr, file=sys.stderr)


def _write_notebook(path: Path) -> None:
    sources = [
        """from sqlalchemy import text
from sql_notebook_kit import create_session

session = create_session(
    backend="duckdb",
    connection_kwargs={"database": "browser-smoke.duckdb"},
)
with session.engine.begin() as connection:
    connection.execute(text("drop table if exists browser_data"))
    connection.execute(text(
        "create table browser_data as "
        "select * from (values (1, 'alpha'), (2, 'beta'), (3, 'gamma')) "
        "as source(amount, category)"
    ))
session.register(visualization=True, max_rows=2)
""",
        """%%sql
select * from browser_data order by 1
""",
        """%%sql
drop table browser_data;
create table browser_data(replacement integer);
insert into browser_data values (10), (20), (30);
""",
        """%%sql
drop table browser_data;
create table browser_data as
select * from (values (1, 'alpha'), (2, 'beta'), (3, 'gamma'))
as source(amount, category);
""",
        """%sql select * from browser_table_that_does_not_exist
""",
    ]
    notebook = nbformat.v4.new_notebook(
        cells=[
            nbformat.v4.new_code_cell(source, id=f"browser-smoke-{index}")
            for index, source in enumerate(sources)
        ],
        metadata={
            "kernelspec": {
                "display_name": "Python 3 (ipykernel)",
                "language": "python",
                "name": "python3",
            }
        },
    )
    nbformat.write(notebook, path)


def _execute_cell(page: object, cells: object, index: int) -> None:
    cell = cells.nth(index)  # type: ignore[attr-defined]
    prompt = cell.locator(".jp-InputPrompt")
    previous = prompt.inner_text()
    cell.scroll_into_view_if_needed()
    # JupyterLab's virtualized notebook can briefly leave sidebar or cell-shell
    # layers above the editor while it settles after scrolling. The editor is
    # already visible here; force the focus click so that transient shell
    # hit-testing does not make the release smoke flaky.
    cell.locator(".cm-content").click(position={"x": 5, "y": 5}, force=True)
    page.keyboard.press("Shift+Enter")  # type: ignore[attr-defined]
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        current = prompt.inner_text()
        if current != previous and "*" not in current and current.strip() not in {"", "[ ]:"}:
            return
        page.wait_for_timeout(100)  # type: ignore[attr-defined]
    raise AssertionError(f"cell {index} did not finish execution; prompt stayed {previous!r}")


def _fill_named_control(workspace: object, label: str, value: str) -> None:
    control = workspace.locator(f".snk-{label.lower()}-control input")  # type: ignore[attr-defined]
    control.fill(value)


def _dispatch_click(locator: object) -> None:
    """Activate a widget without depending on JupyterLab's transient overlays."""
    locator.evaluate("element => element.click()")  # type: ignore[attr-defined]


def test_full_jupyterlab_sql_visualization_lifecycle(tmp_path: Path) -> None:
    from playwright import sync_api as playwright
    _write_notebook(tmp_path / "browser-smoke.ipynb")
    with _jupyter_lab(tmp_path) as url, playwright.sync_playwright() as runtime:
        executable = shutil.which("chromium") or shutil.which("chromium-browser")
        launch = {"headless": True, "args": ["--no-sandbox"]}
        if executable:
            launch["executable_path"] = executable
        browser = runtime.chromium.launch(**launch)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        browser_messages: list[str] = []
        page.on("console", lambda message: browser_messages.append(message.text))
        page.on("pageerror", lambda error: browser_messages.append(str(error)))
        page.on(
            "requestfailed",
            lambda request: browser_messages.append(
                f"request failed: {request.url}: {request.failure}"
            ),
        )
        page.on(
            "response",
            lambda response: (
                browser_messages.append(f"HTTP {response.status}: {response.url}")
                if response.status >= 400
                else None
            ),
        )
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            cells = page.locator(".jp-Notebook .jp-Cell")
            try:
                cells.nth(4).wait_for(timeout=30_000)
            except playwright.TimeoutError as exc:
                diagnostics = "\n".join(browser_messages[-20:])
                raise AssertionError(
                    f"notebook cells did not load; url={page.url!r}; "
                    f"browser messages:\n{diagnostics}"
                ) from exc

            _execute_cell(page, cells, 0)
            _execute_cell(page, cells, 1)
            workspace = cells.nth(1).locator(".snk-viz-workspace")
            workspace.wait_for(timeout=30_000)
            assert "Result truncated to 2 local rows" in workspace.inner_text()
            assert "alpha" in workspace.inner_text()
            assert "gamma" not in workspace.inner_text()

            _dispatch_click(workspace.locator(".snk-add-tab"))
            _fill_named_control(workspace, "name", "Browser chart")
            apply = workspace.get_by_role("button", name="Apply")
            apply.wait_for(state="visible")
            _dispatch_click(apply)
            workspace.get_by_role("button", name="Browser chart").wait_for()

            _dispatch_click(workspace.get_by_role("button", name="Edit"))
            _fill_named_control(workspace, "name", "Browser chart edited")
            _dispatch_click(workspace.get_by_role("button", name="Apply"))
            workspace.get_by_role("button", name="Browser chart edited").wait_for()

            _execute_cell(page, cells, 1)
            workspace = cells.nth(1).locator(".snk-viz-workspace")
            workspace.get_by_role("button", name="Browser chart edited").wait_for(
                timeout=30_000
            )

            _execute_cell(page, cells, 2)
            _execute_cell(page, cells, 1)
            workspace = cells.nth(1).locator(".snk-viz-workspace")
            workspace.get_by_text("Needs attention", exact=False).wait_for(timeout=30_000)

            _execute_cell(page, cells, 3)
            _execute_cell(page, cells, 1)
            workspace = cells.nth(1).locator(".snk-viz-workspace")
            workspace.get_by_role("button", name="Browser chart edited").wait_for(
                timeout=30_000
            )

            page.get_by_text("Settings", exact=True).click()
            page.get_by_text("Theme", exact=True).hover()
            page.get_by_text("JupyterLab Dark", exact=True).click()
            cells.nth(1).locator(".snk-viz-workspace.snk-theme-dark").wait_for(
                timeout=15_000
            )

            page.set_viewport_size({"width": 640, "height": 900})
            page.evaluate("document.documentElement.style.zoom = '200%'")
            page.emulate_media(forced_colors="active")
            add_button = workspace.locator(".snk-add-tab")
            add_button.focus()
            page.keyboard.press("Enter")
            editor = workspace.locator(".snk-editor-panel")
            editor.wait_for()
            assert editor.locator('[role="status"][aria-live="assertive"]').count() == 1
            _fill_named_control(workspace, "name", "")
            editor.locator('[role="alert"]').wait_for(timeout=15_000)
            cancel = editor.get_by_role("button", name="Cancel")
            cancel.focus()
            page.keyboard.press("Enter")
            editor.wait_for(state="detached")
            assert add_button.is_visible()

            delete = workspace.get_by_role("button", name="Delete")
            box = delete.bounding_box()
            assert box is not None
            assert box["x"] >= 0
            assert box["x"] + box["width"] <= 640
            delete.focus()
            page.keyboard.press("Enter")
            delete_dialog = workspace.locator(".snk-dialog-panel")
            delete_dialog.get_by_role("alert").wait_for()
            confirm_delete = delete_dialog.get_by_role("button", name="Delete")
            confirm_delete.focus()
            page.keyboard.press("Enter")
            workspace.get_by_role("button", name="Browser chart edited").wait_for(
                state="detached"
            )

            page.evaluate("document.documentElement.style.zoom = '100%'")
            page.set_viewport_size({"width": 1280, "height": 900})
            page.emulate_media(forced_colors="none")
            _execute_cell(page, cells, 4)
            summary = cells.nth(4).locator(".snk-sql-error-summary")
            # JupyterLab may virtualize the completed cell immediately after
            # execution; its renderer must exist even if its shell is off-screen.
            summary.wait_for(state="attached", timeout=30_000)
            message = summary.inner_text()
            assert message
            assert "Traceback" not in message
            assert "/home/" not in message
            assert "duckdb://" not in message
        finally:
            browser.close()
