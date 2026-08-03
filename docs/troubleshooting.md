# Troubleshooting

| Symptom | Likely cause | Action |
| --- | --- | --- |
| Redshift dialect import fails | Optional driver is absent | Install `redshift-notebooks[redshift]` in the active kernel. |
| Factory module cannot be imported | Kernel environment differs from the terminal | Install the factory package in the selected kernel and verify the dotted reference. |
| Browser never opens | Login is lazy or kernel is headless | Call `session.login()`; for headless kernels use a suitable custom token/device factory. |
| Callback port is occupied | Another process or login owns the port | Configure a different `listen_port` supported by the SSO driver. |
| Login times out | Identity provider, callback, VPN, DNS, or proxy is unavailable | Verify network prerequisites and increase the provider timeout if appropriate. |
| A SQL cell fails | Redshift aborted the cell's active transaction | Managed `%%sql` cells roll back automatically. If recovery itself warns or the connection is unusable, try `%sql ROLLBACK`; otherwise call `session.reconnect()`. Failed statements are never replayed. |
| Query fails after a long session | Connection or temporary credentials became invalid | Call `session.reconnect()` and rerun only after checking whether the previous statement committed. |
| Visualization extra warning | Plotly, pandas, ipywidgets, or nbformat is absent | Install or upgrade `redshift-notebooks[viz]` in the active kernel and restart it. |
| Plotly reports that `nbformat>=4.2.0` is not installed | The kernel has an older visualization extra without its notebook-rendering dependency | Upgrade `redshift-notebooks[viz]` in the active kernel and restart it. |
| Widget controls render as text | Notebook frontend lacks widget support | Enable ipywidgets support in JupyterLab or select a compatible VS Code kernel. |
| Truncation banner appears | More than `max_rows` were returned | Aggregate or filter in SQL; increase the local bound only when memory use is acceptable. |

Error reports should include the exception type, safe profile name, package
versions, and whether the kernel is local or remote. Never attach TOML files,
environment dumps, tokens, SAML responses, or complete connection arguments.
