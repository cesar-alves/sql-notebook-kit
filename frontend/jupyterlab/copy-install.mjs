import { copyFileSync } from 'node:fs';
import { resolve } from 'node:path';

copyFileSync(
  resolve('frontend/jupyterlab/install.json'),
  resolve('redshift_notebooks/labextension/install.json')
);
