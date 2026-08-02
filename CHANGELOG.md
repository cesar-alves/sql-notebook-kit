# Changelog

## 0.1.0

- Define a synchronous DBAPI connection-factory contract and managed notebook session.
- Add named profiles, environment/secret resolution, and reference browser SSO factories.
- Add bounded `NotebookResult` output and optional Plotly/ipywidgets visualization.
- Require pandas 3.0.5 or newer for visualization and cover pandas 3 dtype,
  copy-on-write, aggregation, export, and rendering behavior.
- Add reusable factory contract testing, public API documentation, and package quality gates.
- Roll back failed managed `%%sql` transactions so one SQL error does not poison
  the rest of the notebook session.
