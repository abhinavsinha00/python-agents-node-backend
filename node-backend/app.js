'use strict';

const fs = require('node:fs');
const express = require('express');
const { loadConfig } = require('./config');
const { JobManager } = require('./job-manager');

function createApp({ config = loadConfig(), jobManager = new JobManager(config) } = {}) {
  const app = express();
  app.disable('x-powered-by');
  app.use(express.json({ limit: '16kb', strict: true }));

  app.get('/api/health', (_request, response) => {
    const stats = jobManager.stats();
    response.status(200).json({
      success: true,
      data: {
        status: 'ok',
        runtime: {
          nodeVersion: process.version,
          port: config.port,
          pythonExecutableSource: config.pythonExecutableSource,
          pythonExecutableConfigured: Boolean(config.pythonExecutable),
          projectEnvFilePresent: fs.existsSync(`${config.repositoryRoot}/.env`),
          maxConcurrentBuilds: config.maxConcurrentBuilds,
          activeBuilds: stats.activeBuilds,
          queuedBuilds: stats.queuedBuilds,
        },
      },
    });
  });

  app.post('/api/build', (request, response, next) => {
    const { platform, requirement } = request.body || {};
    if (platform !== 'web' && platform !== 'mobile') {
      response.status(400).json({ success: false, error: { code: 'INVALID_PLATFORM', message: "platform must be 'web' or 'mobile'." } });
      return;
    }
    if (typeof requirement !== 'string' || !requirement.trim()) {
      response.status(400).json({ success: false, error: { code: 'INVALID_REQUIREMENT', message: 'requirement must be a non-empty string.' } });
      return;
    }
    if (requirement.trim().length > config.maxRequirementLength) {
      response.status(400).json({ success: false, error: { code: 'REQUIREMENT_TOO_LONG', message: `requirement must be at most ${config.maxRequirementLength} characters.` } });
      return;
    }
    try {
      const job = jobManager.submit({ platform, requirement: requirement.trim() });
      response.status(202).json({
        success: true,
        data: {
          jobId: job.id,
          status: job.status,
          statusUrl: `/api/jobs/${job.id}`,
        },
      });
    } catch (error) {
      if (error.code === 'BUILD_CAPACITY') {
        response.status(503).json({ success: false, error: { code: error.code, message: error.message } });
        return;
      }
      next(error);
    }
  });

  app.get('/api/jobs/:jobId', (request, response) => {
    const job = jobManager.get(request.params.jobId);
    if (!job) {
      response.status(404).json({ success: false, error: { code: 'JOB_NOT_FOUND', message: 'Build job was not found.' } });
      return;
    }
    response.status(200).json({ success: true, data: job });
  });

  app.use((error, _request, response, _next) => {
    if (error.type === 'entity.parse.failed') {
      response.status(400).json({ success: false, error: { code: 'INVALID_JSON', message: 'Request body must contain valid JSON.' } });
      return;
    }
    if (error.type === 'entity.too.large') {
      response.status(413).json({ success: false, error: { code: 'BODY_TOO_LARGE', message: 'Request body exceeds the 16 KB limit.' } });
      return;
    }
    response.status(500).json({ success: false, error: { code: 'INTERNAL_ERROR', message: 'An unexpected backend error occurred.' } });
  });

  return app;
}

module.exports = { createApp };