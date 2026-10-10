'use strict';

const fs = require('node:fs');
const path = require('node:path');
require('dotenv').config({ path: path.join(__dirname, '.env'), quiet: true });

const repositoryRoot = path.resolve(__dirname, '..');

function positiveInteger(value, fallback, maximum) {
  const parsed = Number.parseInt(value, 10);
  return Number.isInteger(parsed) && parsed > 0 ? Math.min(parsed, maximum) : fallback;
}

function resolvePythonExecutable(env = process.env, platform = process.platform) {
  if (env.PYTHON_EXECUTABLE && env.PYTHON_EXECUTABLE.trim()) {
    return { executable: env.PYTHON_EXECUTABLE.trim(), source: 'PYTHON_EXECUTABLE' };
  }

  const localPython = platform === 'win32'
    ? path.join(repositoryRoot, '.venv', 'Scripts', 'python.exe')
    : path.join(repositoryRoot, '.venv', 'bin', 'python');
  if (fs.existsSync(localPython)) {
    return { executable: localPython, source: '.venv' };
  }
  return { executable: platform === 'win32' ? 'python' : 'python3', source: 'PATH fallback' };
}

function loadConfig(env = process.env) {
  const python = resolvePythonExecutable(env);
  return {
    repositoryRoot,
    bridgePath: path.join(repositoryRoot, 'agent_api_runner.py'),
    outputRoot: path.join(repositoryRoot, 'output'),
    port: positiveInteger(env.PORT, 3000, 65535),
    maxConcurrentBuilds: positiveInteger(env.MAX_CONCURRENT_BUILDS, 1, 8),
    maxQueuedBuilds: positiveInteger(env.MAX_QUEUED_BUILDS, 20, 200),
    buildTimeoutMs: positiveInteger(env.BUILD_TIMEOUT_MS, 30 * 60 * 1000, 60 * 60 * 1000),
    maxRequirementLength: 8000,
    pythonExecutable: python.executable,
    pythonExecutableSource: python.source,
  };
}

module.exports = { loadConfig, resolvePythonExecutable };