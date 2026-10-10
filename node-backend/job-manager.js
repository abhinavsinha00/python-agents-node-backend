'use strict';

const { randomUUID } = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const { runPythonBuild, sanitizeLog } = require('./python-runner');

const MAX_RECENT_LOGS = 100;

function collectGeneratedFiles(projectPath, outputRoot) {
  const root = path.resolve(outputRoot);
  const project = path.resolve(projectPath);
  const relative = path.relative(root, project);
  if (relative === '..' || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative) || !fs.existsSync(project)) return [];
  const files = [];
  function visit(directory) {
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      const target = path.join(directory, entry.name);
      if (entry.isSymbolicLink()) continue;
      if (entry.isDirectory()) visit(target);
      else if (entry.isFile()) files.push(path.relative(project, target).split(path.sep).join('/'));
    }
  }
  visit(project);
  return files.sort();
}

class JobManager {
  constructor(config, runner = runPythonBuild) {
    this.config = config;
    this.runner = runner;
    this.jobs = new Map();
    this.queue = [];
    this.activeBuilds = 0;
  }

  submit({ platform, requirement }) {
    if (this.queue.length + this.activeBuilds >= this.config.maxQueuedBuilds + this.config.maxConcurrentBuilds) {
      const error = new Error('Build queue is full; try again later.');
      error.code = 'BUILD_CAPACITY';
      throw error;
    }
    const id = randomUUID();
    const projectId = `${platform}-${id}`;
    const job = {
      id,
      projectId,
      platform,
      requirement,
      status: 'queued',
      createdAt: new Date().toISOString(),
      startedAt: null,
      completedAt: null,
      progress: { stage: 'queued', percent: 0, message: 'Waiting for an available agent slot.' },
      recentLogs: [],
      result: null,
      error: null,
      projectPath: path.resolve(this.config.outputRoot, projectId),
    };
    this.jobs.set(id, job);
    this.queue.push(id);
    this.drain();
    return this.toPublic(job);
  }

  get(id) {
    const job = this.jobs.get(id);
    return job ? this.toPublic(job) : null;
  }

  stats() {
    return { activeBuilds: this.activeBuilds, queuedBuilds: this.queue.length };
  }

  toPublic(job) {
    const { requirement, ...publicJob } = job;
    return structuredClone(publicJob);
  }

  addLog(job, line) {
    job.recentLogs.push({ timestamp: new Date().toISOString(), message: sanitizeLog(line) });
    if (job.recentLogs.length > MAX_RECENT_LOGS) job.recentLogs.splice(0, job.recentLogs.length - MAX_RECENT_LOGS);
  }

  drain() {
    while (this.activeBuilds < this.config.maxConcurrentBuilds && this.queue.length > 0) {
      const id = this.queue.shift();
      const job = this.jobs.get(id);
      if (!job) continue;
      this.activeBuilds += 1;
      job.status = 'running';
      job.startedAt = new Date().toISOString();
      job.progress = { stage: 'starting', percent: 1, message: 'Starting Python agent process.' };
      void this.execute(job);
    }
  }

  async execute(job) {
    try {
      const result = await this.runner(job, this.config, {
        onLog: (line) => this.addLog(job, line),
        onProgress: (progress) => {
          const percent = Number.isFinite(progress.percent) ? Math.max(0, Math.min(100, progress.percent)) : job.progress.percent;
          job.progress = {
            stage: String(progress.stage || job.progress.stage).slice(0, 100),
            percent,
            message: sanitizeLog(progress.message || '').slice(0, 300),
          };
        },
      });
      job.result = result;
      job.projectPath = result.projectPath || job.projectPath;
      if (result.status === 'succeeded') {
        job.status = 'succeeded';
        job.progress = { stage: 'complete', percent: 100, message: result.message || 'Build completed.' };
      } else {
        job.status = 'failed';
        job.error = result.error || { type: 'BuildFailed', message: result.message || 'Agent workflow failed.' };
        job.progress = { ...job.progress, stage: 'failed', message: job.error.message };
      }
    } catch (error) {
      job.status = 'failed';
      job.error = { type: 'PythonProcessError', message: sanitizeLog(error.message).slice(0, 2_000) };
      job.result = {
        jobId: job.id,
        projectId: job.projectId,
        platform: job.platform,
        status: 'failed',
        projectPath: job.projectPath,
        generatedFiles: collectGeneratedFiles(job.projectPath, this.config.outputRoot),
        finalUrl: null,
        message: 'Python agent process failed.',
        error: job.error,
      };
      job.progress = { ...job.progress, stage: 'failed', message: job.error.message };
      this.addLog(job, job.error.message);
    } finally {
      job.completedAt = new Date().toISOString();
      this.activeBuilds -= 1;
      this.drain();
    }
  }
}

module.exports = { JobManager };