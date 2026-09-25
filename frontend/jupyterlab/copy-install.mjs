import { copyFileSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

copyFileSync(
  resolve('frontend/jupyterlab/install.json'),
  resolve('sql_notebook_kit/labextension/install.json')
);

const generatedStyle = resolve('sql_notebook_kit/labextension/static/style.js');
writeFileSync(generatedStyle, `${readFileSync(generatedStyle, 'utf8').trimEnd()}\n`);
