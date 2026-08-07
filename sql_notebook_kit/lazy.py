"""Safe lazy SQLFrame transformations for managed notebook sessions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sql_notebook_kit.errors import ConfigurationError, LazyQueryError, StaleLazyQueryError
from sql_notebook_kit.results import NotebookResult


def validate_relation_query(query: str) -> str | None:
    """Return an ineligibility reason, or ``None`` for one SELECT relation."""
    try:
        import sqlparse
    except ImportError as exc:  # pragma: no cover - JupySQL installs sqlparse
        raise ConfigurationError("SQL parsing support is unavailable") from exc

    statements = [statement for statement in sqlparse.parse(query) if str(statement).strip()]
    if len(statements) != 1:
        return "only one SQL statement can be transformed lazily"
    if statements[0].get_type().upper() != "SELECT":
        return "only relation-producing SELECT statements can be transformed lazily"
    if any(
        token.ttype is sqlparse.tokens.Name.Placeholder
        for token in statements[0].flatten()
    ):
        return "unresolved bind parameters cannot be captured safely"
    return None


@dataclass(frozen=True, slots=True, repr=False)
class LazyQuery:
    """An immutable, bounded wrapper around a SQLFrame transformation plan."""

    _session: Any = field(repr=False)
    _source_sql: str = field(repr=False)
    _generation: int
    _native_df: Any = field(default=None, repr=False)

    def __repr__(self) -> str:
        state = "transformed" if self._native_df is not None else "source"
        return f"<LazyQuery state={state!r}>"

    def _assert_live(self) -> None:
        if self._generation != self._session._transform_generation:
            raise StaleLazyQueryError(
                "this lazy query was invalidated by reconnect() or dispose(); "
                "rerun its SQL cell to create a fresh _df"
            )

    @property
    def native(self) -> Any:
        """Return the native SQLFrame DataFrame, creating it lazily."""
        self._assert_live()
        if self._native_df is not None:
            return self._native_df
        return self._session._create_transform_dataframe(self._source_sql)

    def apply(self, transform: Callable[[object], object]) -> LazyQuery:
        """Apply a SQLFrame transformation without mutating this query."""
        native = self.native
        try:
            transformed = transform(native)
        except Exception as exc:
            raise LazyQueryError(
                f"the lazy transformation failed ({type(exc).__name__})"
            ) from exc
        if transformed is None or not callable(getattr(transformed, "sql", None)):
            raise LazyQueryError("the transform must return a SQLFrame DataFrame")
        if getattr(transformed, "session", None) is not getattr(native, "session", None):
            raise LazyQueryError(
                "the transform returned a DataFrame from a different transform session"
            )
        return LazyQuery(
            self._session,
            self._source_sql,
            self._generation,
            transformed,
        )

    def compile(self, *, optimized: bool = False) -> str:
        """Compile the transformation plan without executing warehouse SQL."""
        try:
            compiled = self.native.sql(optimize=optimized)
        except (ConfigurationError, LazyQueryError):
            raise
        except Exception as exc:
            raise LazyQueryError(
                f"lazy compilation failed ({type(exc).__name__})"
            ) from exc
        if not isinstance(compiled, str):
            raise LazyQueryError("SQLFrame returned an invalid compiled SQL value")
        return compiled

    def collect(
        self,
        *,
        max_rows: int = 10_000,
        allow_large_results: bool = False,
    ) -> NotebookResult:
        """Execute with an outer bounded limit and return detached local data."""
        if max_rows < 1:
            raise ConfigurationError("max_rows must be positive")
        if max_rows > 100_000 and not allow_large_results:
            raise ConfigurationError("max_rows above 100000 requires allow_large_results=True")
        self._assert_live()
        try:
            frame = self.native.limit(max_rows + 1).toPandas()
            truncated = len(frame) > max_rows
            bounded = frame.iloc[:max_rows].copy()
        except LazyQueryError:
            raise
        except Exception as exc:
            raise LazyQueryError(f"lazy collection failed ({type(exc).__name__})") from exc
        return NotebookResult(
            dataframe=bounded,
            raw=None,
            truncated=truncated,
            max_rows=max_rows,
        )

    def visualize(
        self,
        *,
        max_rows: int = 10_000,
        allow_large_results: bool = False,
    ) -> object:
        """Collect a bounded result and open its visualization workspace."""
        return self.collect(
            max_rows=max_rows, allow_large_results=allow_large_results
        ).visualize()
