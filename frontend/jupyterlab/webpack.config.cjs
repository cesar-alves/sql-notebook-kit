const path = require('node:path');

module.exports = {
  // Rspack's deterministic IDs are relative to the build context. Pin the
  // context to this package so checkout location never changes bundle hashes
  // for the same source and lockfile while loaders still resolve locally.
  context: path.resolve(__dirname),
  optimization: {
    // Natural IDs are assigned from the stable locked module graph. Rspack's
    // hashed "deterministic" IDs include real checkout paths for linked workspaces.
    chunkIds: 'natural',
    moduleIds: 'natural'
  }
};
