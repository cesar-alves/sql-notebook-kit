import { copyFileSync, mkdirSync, readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const manifest = JSON.parse(readFileSync(resolve(here, 'package.json'), 'utf8'));
const source = resolve(here, `${manifest.name}-${manifest.version}.vsix`);
const target = resolve(here, '../../redshift_notebooks/vscode/redshift-notebooks-vscode.vsix');
mkdirSync(dirname(target), { recursive: true });
copyFileSync(source, target);
console.log(`Staged ${source} -> ${target}`);
