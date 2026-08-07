import { copyFileSync } from 'node:fs';
import { resolve } from 'node:path';

copyFileSync(
  resolve('frontend/jupyterlab/install.json'),
  resolve('sql_notebook_kit/labextension/install.json')
);
