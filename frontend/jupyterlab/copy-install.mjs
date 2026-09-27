import { copyFileSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

copyFileSync(
  resolve('frontend/jupyterlab/install.json'),
  resolve('sql_notebook_kit/labextension/install.json')
);

const generatedStyle = resolve('sql_notebook_kit/labextension/static/style.js');
writeFileSync(generatedStyle, `${readFileSync(generatedStyle, 'utf8').trimEnd()}\n`);

const generatedManifest = resolve('sql_notebook_kit/labextension/package.json');
const manifest = JSON.parse(readFileSync(generatedManifest, 'utf8'));
delete manifest.jupyterlab.webpackConfig;
writeFileSync(generatedManifest, `${JSON.stringify(manifest, null, 2)}\n`);
