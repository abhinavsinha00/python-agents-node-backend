'use strict';

const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const { PassThrough } = require('node:stream');
const test = require('node:test');
const { runPythonBuild } = require('../python-runner');

function config(overrides = {}) {
  return {
    pythonExecutable: 'python-test',
    bridgePath: 'agent_api_runner.py',
    repositoryRoot: 'C:/repo',
    outputRoot: 'C:/repo/output',
    buildTimeoutMs: 500,
    ...overrides,
  };
}

function fakeChild({ output = '', errorOutput = '', code = 0, processError = null, hold = false } = {}) {
  const child = new EventEmitter();
  child.stdout = new PassThrough();
  child.stderr = new PassThrough();
  child.stdin = new PassThrough();
  child.kill = () => true;
  child.stdin.on('finish', () => {
    if (hold) return;
    setImmediate(() => {
      if (processError) {
        child.emit('error', processError);
        return;
      }
      if (output) child.stdout.write(output);
      child.stdout.end();
      if (errorOutput) child.stderr.write(errorOutput);
      child.stderr.end();
      child.emit('close', code, null);
    });
  });
  return child;
}

function job(overrides = {}) {
  return { id: '11111111-1111-4111-8111-111111111111', platform: 'web', requirement: 'Build a page', projectId: 'web-11111111-1111-4111-8111-111111111111', ...overrides };
}

function bridgeResult(currentJob, overrides = {}) {
  return JSON.stringify({
    jobId: currentJob.id,
    projectId: currentJob.projectId,
    platform: currentJob.platform,
    status: 'succeeded',
    projectPath: `C:/repo/output/${currentJob.projectId}`,
    generatedFiles: ['index.html'],
    finalUrl: null,
    message: 'Completed',
    error: null,
    ...overrides,
  });
}

test('Python runner uses spawn without a shell and sends structured stdin', async () => {
  const currentJob = job();
  let spawnArgs;
  let child;
  const run = runPythonBuild(currentJob, config(), {
    spawnImpl: (...args) => {
      spawnArgs = args;
      child = fakeChild({ output: bridgeResult(currentJob) });
      child.stdin.on('data', () => {});
      return child;
    },
  });
  const result = await run;
  assert.equal(spawnArgs[0], 'python-test');
  assert.deepEqual(spawnArgs[1], ['-u', 'agent_api_runner.py']);
  assert.equal(spawnArgs[2].shell, false);
  assert.equal(spawnArgs[2].cwd, 'C:/repo');
  assert.equal(result.status, 'succeeded');
});

test('Python runner accepts a structured failed result on a nonzero exit', async () => {
  const currentJob = job({ platform: 'mobile' });
  const result = await runPythonBuild(currentJob, config(), {
    spawnImpl: () => fakeChild({
      output: bridgeResult(currentJob, { status: 'failed', error: { type: 'MobileQAFailed', message: 'QA failed' } }),
      code: 1,
    }),
  });
  assert.equal(result.status, 'failed');
  assert.equal(result.error.type, 'MobileQAFailed');
});

test('Python runner rejects malformed output, process errors, and synchronous spawn failures', async () => {
  await assert.rejects(
    runPythonBuild(job(), config(), { spawnImpl: () => fakeChild({ output: 'not json' }) }),
    /malformed JSON/,
  );
  await assert.rejects(
    runPythonBuild(job(), config(), { spawnImpl: () => fakeChild({ processError: new Error('missing python') }) }),
    /process error/,
  );
  await assert.rejects(
    runPythonBuild(job(), config(), { spawnImpl: () => { throw new Error('spawn denied'); } }),
    /Could not start Python bridge/,
  );
});

test('Python runner rejects unsafe output paths and times out hung processes', async () => {
  const currentJob = job();
  await assert.rejects(
    runPythonBuild(currentJob, config(), {
      spawnImpl: () => fakeChild({ output: bridgeResult(currentJob, { projectPath: 'C:/outside/project' }) }),
    }),
    /unsafe project path/,
  );

  const hungChild = fakeChild({ hold: true });
  let wasKilled = false;
  hungChild.kill = () => { wasKilled = true; return true; };
  await assert.rejects(
    runPythonBuild(currentJob, config({ buildTimeoutMs: 20 }), { spawnImpl: () => hungChild }),
    /exceeded timeout/,
  );
  assert.equal(wasKilled, true);
});