'use strict';

const assert = require('node:assert/strict');
const http = require('node:http');
const path = require('node:path');
const test = require('node:test');
const { createApp } = require('../app');
const { JobManager } = require('../job-manager');

function testConfig() {
  return {
    repositoryRoot: path.resolve(__dirname, '../..'),
    outputRoot: path.resolve(__dirname, '../../output'),
    maxConcurrentBuilds: 1,
    maxQueuedBuilds: 3,
    maxRequirementLength: 8000,
  };
}

async function startApi(t, jobManager, config = testConfig()) {
  const server = http.createServer(createApp({ config, jobManager }));
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  t.after(() => new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve())));
  return `http://127.0.0.1:${server.address().port}`;
}

async function waitForStatus(baseUrl, jobId, status) {
  for (let attempt = 0; attempt < 50; attempt += 1) {
    const response = await fetch(`${baseUrl}/api/jobs/${jobId}`);
    const { data } = await response.json();
    if (data.status === status) return data;
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
  assert.fail(`Job ${jobId} did not reach ${status}`);
}

test('health reports runtime status without exposing secrets', async (t) => {
  const config = testConfig();
  config.pythonExecutableSource = '.venv';
  config.pythonExecutable = 'python-test';
  const manager = new JobManager(config, async () => ({}));
  const baseUrl = await startApi(t, manager, config);
  const response = await fetch(`${baseUrl}/api/health`);
  const body = await response.json();
  assert.equal(response.status, 200);
  assert.equal(body.success, true);
  assert.equal(body.data.status, 'ok');
  assert.equal(body.data.runtime.pythonExecutableSource, '.venv');
  assert.equal(JSON.stringify(body).includes('TARGET_API_KEY'), false);
});

test('build endpoint validates input and returns 202 with a status URL', async (t) => {
  const manager = new JobManager(testConfig(), async (job) => ({
    jobId: job.id,
    projectId: job.projectId,
    platform: job.platform,
    status: 'succeeded',
    projectPath: job.projectPath,
    generatedFiles: ['index.html'],
    finalUrl: null,
    message: 'Done',
    error: null,
  }));
  const baseUrl = await startApi(t, manager);

  for (const body of [
    { platform: 'desktop', requirement: 'x' },
    { platform: 'web', requirement: '   ' },
    { platform: 'web', requirement: 'x'.repeat(8001) },
  ]) {
    const response = await fetch(`${baseUrl}/api/build`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    });
    assert.equal(response.status, 400);
    assert.equal((await response.json()).success, false);
  }

  const accepted = await fetch(`${baseUrl}/api/build`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ platform: 'web', requirement: 'Build a calculator.' }),
  });
  const body = await accepted.json();
  assert.equal(accepted.status, 202);
  assert.equal(body.data.status, 'running');
  assert.match(body.data.statusUrl, new RegExp(`/api/jobs/${body.data.jobId}$`));
});

test('job endpoint reports unknown IDs as 404', async (t) => {
  const baseUrl = await startApi(t, new JobManager(testConfig(), async () => ({})));
  const response = await fetch(`${baseUrl}/api/jobs/not-a-job`);
  assert.equal(response.status, 404);
  assert.equal((await response.json()).error.code, 'JOB_NOT_FOUND');
});

test('job status transitions from running to succeeded with progress and result', async (t) => {
  let resolveRun;
  let markStarted;
  const started = new Promise((resolve) => { markStarted = resolve; });
  const manager = new JobManager(testConfig(), (job, _config, callbacks) => {
    callbacks.onProgress({ stage: 'developer', percent: 60, message: 'Writing files' });
    callbacks.onLog('agent stage started');
    markStarted();
    return new Promise((resolve) => { resolveRun = () => resolve({
      jobId: job.id,
      projectId: job.projectId,
      platform: job.platform,
      status: 'succeeded',
      projectPath: job.projectPath,
      generatedFiles: ['index.html'],
      finalUrl: null,
      message: 'Build completed',
      error: null,
    }); });
  });
  const baseUrl = await startApi(t, manager);
  const acceptedResponse = await fetch(`${baseUrl}/api/build`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ platform: 'web', requirement: 'Build a page' }),
  });
  const accepted = await acceptedResponse.json();
  await started;
  const running = await (await fetch(`${baseUrl}${accepted.data.statusUrl}`)).json();
  assert.equal(running.data.status, 'running');
  assert.equal(running.data.progress.stage, 'developer');
  assert.equal(running.data.recentLogs[0].message, 'agent stage started');

  resolveRun();
  const completed = await waitForStatus(baseUrl, accepted.data.jobId, 'succeeded');
  assert.equal(completed.result.generatedFiles[0], 'index.html');
  assert.ok(completed.startedAt);
  assert.ok(completed.completedAt);
});

test('Web and Mobile jobs route correctly and preserve actual failures', async (t) => {
  const seenPlatforms = [];
  const manager = new JobManager(testConfig(), async (job) => {
    seenPlatforms.push(job.platform);
    return job.platform === 'web'
      ? { jobId: job.id, projectId: job.projectId, platform: 'web', status: 'succeeded', projectPath: job.projectPath, generatedFiles: ['index.html'], finalUrl: 'http://127.0.0.1:8000/demo/', message: 'Web completed', error: null }
      : { jobId: job.id, projectId: job.projectId, platform: 'mobile', status: 'failed', projectPath: job.projectPath, generatedFiles: [], finalUrl: null, message: 'Mobile failed', error: { type: 'MobileQAFailed', message: 'QA reported failure' } };
  });
  const baseUrl = await startApi(t, manager);

  async function createJob(platform) {
    const response = await fetch(`${baseUrl}/api/build`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ platform, requirement: 'Build a project' }),
    });
    return (await response.json()).data;
  }

  const webJob = await createJob('web');
  const web = await waitForStatus(baseUrl, webJob.jobId, 'succeeded');
  assert.equal(web.result.finalUrl, 'http://127.0.0.1:8000/demo/');
  const mobileJob = await createJob('mobile');
  const mobile = await waitForStatus(baseUrl, mobileJob.jobId, 'failed');
  assert.deepEqual(seenPlatforms, ['web', 'mobile']);
  assert.equal(mobile.error.type, 'MobileQAFailed');
  assert.equal(mobile.result.finalUrl, null);
});