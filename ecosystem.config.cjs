module.exports = {
  apps: [
    {
      name: 'ai-audio-backend',
      cwd: '/workspace/backend',
      script: 'main.py',
      interpreter: 'python3',
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '1G',
      env: {
        NODE_ENV: 'development',
        HOST: '0.0.0.0',
        PORT: 8000,
      },
      log_file: '/workspace/backend/server.log',
      out_file: '/workspace/backend/server.log',
      error_file: '/workspace/backend/server.log',
      merge_logs: true,
      time: true,
      // 健康检查
      health_check: {
        enabled: true,
        url: 'http://localhost:8000/health',
        interval: 10000,
        timeout: 5000,
        retries: 3,
      },
      // 重启策略
      restart_delay: 3000,
      max_restarts: 10,
      min_uptime: '10s',
    },
    {
      name: 'ai-audio-frontend',
      cwd: '/workspace',
      script: 'npm',
      args: 'run dev',
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '512M',
      env: {
        NODE_ENV: 'development',
      },
      log_file: '/workspace/frontend.log',
      out_file: '/workspace/frontend.log',
      error_file: '/workspace/frontend.log',
      merge_logs: true,
      time: true,
      // 等待后端启动后再启动前端
      wait_ready: true,
      // 依赖后端服务
      depends_on: ['ai-audio-backend'],
    },
  ],
};
