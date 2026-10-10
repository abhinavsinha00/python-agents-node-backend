'use strict';

const { spawn } = require('node:child_process');
const path = require('node:path');

const MAX_STDOUT_BYTES = 1024 * 1024;
const MAX_STDERR_BYTES = 512 * 1024;

function sanitizeLog(text) {
  let sanitized = String(text);
  for (const name of [
    'TARGET_API_KEY',
    'OPENAI_API_KEY',
    'GEMINI_API_KEY',
    'GROQ_API_KEY',
    'ANTHROPIC_API_KEY',
    'DEPLOY_TOKEN',
    'NETLIFY_AUTH_TOKEN',
    'VERCEL_TOKEN',
    'AWS_SECRET_ACCESS_KEY',
  ]) {
    const secret = process.env[name];
    if (secret && secret.length > 3) sanitized = sanitized.split(secret).join('[REDACTED]');
  }
  return sanitized
    .replace(/(api[_ -]?key\s*[:=]\s*)[^\s,;"']+/gi, '$1[REDACTED]')
    .replace(/(token\s*[:=]\s*)[^\s,;"']+/gi, '$1[REDACTED]')
    .replace(/(bearer\s+)[a-zA-Z0-9_.-]+/gi, '$1[REDACTED]')
    .slice(-2000);
}

function isWithin(parent, candidate) {
  const relative = path.relative(parent, candidate);
  return relative === '' || (!relative.startsWith(`..${path.sep}`) && relative !== '..' && !path.isAbsolute(relative));
}

function runPythonBuild(job, config, { onLog = () => {}, onProgress = () => {}, spawnImpl = spawn } = {}) {
  return new Promise((resolve, reject) => {
    let child;
    let stdout = '';
    let stderr = '';
    let stdoutBytes = 0;
    let stderrBytes = 0;
    let stderrPending = '';
    let settled = false;
    let timedOut = false;
    let timer;

    const finish = (error, value) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      if (error) reject(error);
      else resolve(value);
    };

    try {
      child = spawnImpl(config.pythonExecutable, ['-u', config.bridgePath], {
        cwd: config.repositoryRoot,
        shell: false,
        windowsHide: true,
        stdio: ['pipe', 'pipe', 'pipe'],
      });
    } catch (error) {
      finish(new Error(`Could not start Python bridge: ${sanitizeLog(error.message)}`));
      return;
    }

    timer = setTimeout(() => {
      timedOut = true;
      child.kill();
      finish(new Error(`Python build exceeded timeout of ${config.buildTimeoutMs} ms`));
    }, config.buildTimeoutMs);

    child.on('error', (error) => {
      finish(new Error(`Python process error: ${sanitizeLog(error.message)}`));
    });

    child.stdout.on('data', (chunk) => {
      stdoutBytes += Buffer.byteLength(chunk);
      if (stdoutBytes > MAX_STDOUT_BYTES) {
        child.kill();
        finish(new Error('Python bridge output exceeded the allowed size'));
        return;
      }
      stdout += chunk.toString('utf8');
    });

    child.stderr.on('data', (chunk) => {
      stderrBytes += Buffer.byteLength(chunk);
      stderr += chunk.toString('utf8');
      if (stderrBytes > MAX_STDERR_BYTES) {
        stderr = stderr.slice(-MAX_STDERR_BYTES);
        stderrBytes = Buffer.byteLength(stderr);
      }
      stderrPending += chunk.toString('utf8');
      const lines = stderrPending.split(/\r?\n/);
      stderrPending = lines.pop() || '';
      for (const line of lines) consumeDiagnostic(line);
    });

    function consumeDiagnostic(rawLine) {
      const line = sanitizeLog(rawLine.trim());
      if (!line) return;
      if (line.startsWith('AGENT_PROGRESS ')) {
        try {
          const progress = JSON.parse(line.slice('AGENT_PROGRESS '.length));
          onProgress(progress);
          return;
        } catch {
          onLog(line);
          return;
        }
      }
      onLog(line);
    }

    child.on('close', (code, signal) => {
      if (stderrPending.trim()) consumeDiagnostic(stderrPending);
      if (timedOut || settled) return;
      let result;
      try {
        result = JSON.parse(stdout.trim());
      } catch {
        finish(new Error(`Python bridge returned malformed JSON (exit ${code ?? 'unknown'}): ${sanitizeLog(stderr).slice(-500)}`));
        return;
      }
      if (!result || typeof result !== 'object' || Array.isArray(result)) {
        finish(new Error('Python bridge JSON must be an object'));
        return;
      }
      if (result.jobId !== job.id) {
        finish(new Error('Python bridge response jobId did not match the requested job'));
        return;
      }
      if (result.projectId !== job.projectId || result.platform !== job.platform) {
        finish(new Error('Python bridge response project identity did not match the requested job'));
        return;
      }
      if (!['succeeded', 'failed'].includes(result.status)) {
        finish(new Error('Python bridge returned an unsupported job status'));
        return;
      }
      const expectedPath = path.resolve(config.outputRoot, job.projectId);
      if (result.projectPath) {
        const returnedPath = path.resolve(result.projectPath);
        if (!isWithin(path.resolve(config.outputRoot), returnedPath) || returnedPath !== expectedPath) {
          finish(new Error('Python bridge returned an unsafe project path'));
          return;
        }
      }
      result.projectPath = expectedPath;
      result.generatedFiles = Array.isArray(result.generatedFiles)
        ? result.generatedFiles.filter((file) => {
          if (typeof file !== 'string' || !file.trim() || file.includes('\\') || path.posix.isAbsolute(file)) return false;
          const parts = file.split('/');
          return parts.every((part) => part && part !== '.' && part !== '..');
        })
        : [];
      if (code !== 0 && result.status === 'succeeded') {
        finish(new Error(`Python process exited with code ${code ?? signal} after reporting success`));
        return;
      }
      finish(null, result);
    });

    child.stdin.on('error', (error) => {
      if (!settled) finish(new Error(`Could not send request to Python bridge: ${sanitizeLog(error.message)}`));
    });
    child.stdin.end(JSON.stringify({
      jobId: job.id,
      platform: job.platform,
      requirement: job.requirement,
    }));
  });
}

module.exports = { runPythonBuild, sanitizeLog };