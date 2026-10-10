'use strict';

const { createApp } = require('./app');
const { loadConfig } = require('./config');

function startServer(config = loadConfig()) {
  const app = createApp({ config });
  return app.listen(config.port, () => {
    process.stdout.write(`Node agent API listening on port ${config.port}\n`);
  });
}

if (require.main === module) {
  startServer();
}

module.exports = { startServer };