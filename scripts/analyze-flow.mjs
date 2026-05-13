import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');

function safeRead(filePath) {
  try {
    if (!fs.existsSync(filePath)) return null;
    return fs.readFileSync(filePath, 'utf-8');
  } catch { return null; }
}

function safeReaddir(dirPath) {
  try {
    if (!fs.existsSync(dirPath)) return [];
    return fs.readdirSync(dirPath).filter(f => !f.startsWith('.') && !f.endsWith('.map'));
  } catch { return []; }
}

function parseImports(code) {
  if (!code) return [];
  const imports = [];
  const fromRe = /import\s+(?:\{[^}]*\}|\*\s+as\s+\w+|\w+(?:\s*,\s*(?:\{[^}]*\}|\*\s+as\s+\w+|\w+))?)\s+from\s+['"]([^'"]+)['"]/g;
  let m;
  while ((m = fromRe.exec(code)) !== null) {
    imports.push(m[1]);
  }
  const dynamicRe = /import\s*\(\s*['"]([^'"]+)['"]\s*\)/g;
  while ((m = dynamicRe.exec(code)) !== null) {
    imports.push(m[1]);
  }
  return imports;
}

function resolveLocalPath(baseDir, importPath) {
  if (!importPath.startsWith('.') && !importPath.startsWith('@/') && !importPath.startsWith('/')) return null;
  const resolved = importPath.startsWith('@/')
    ? path.join(ROOT, 'src', importPath.slice(2))
    : path.resolve(baseDir, importPath);
  const exts = ['.tsx', '.ts', '.js', '.jsx', '.mjs', ''];
  for (const ext of exts) {
    const p = resolved + ext;
    if (fs.existsSync(p)) return p;
    const index = path.join(resolved, 'index' + ext);
    if (fs.existsSync(index)) return index;
  }
  return null;
}

function classifyImport(importPath) {
  if (importPath.startsWith('@/pages/') || importPath.startsWith('../pages/') || importPath.startsWith('./pages/')) return 'page';
  if (importPath.startsWith('@/components/') || importPath.startsWith('../components/') || importPath.startsWith('./components/')) return 'component';
  if (importPath.startsWith('@/hooks/') || importPath.startsWith('../hooks/') || importPath.startsWith('./hooks/')) return 'hook';
  if (importPath.startsWith('@/services/') || importPath.startsWith('../services/') || importPath.startsWith('./services/')) return 'service';
  if (importPath.startsWith('@/contexts/') || importPath.startsWith('../contexts/') || importPath.startsWith('./contexts/')) return 'context';
  if (importPath.startsWith('@/store/') || importPath.startsWith('../store/') || importPath.startsWith('./store/')) return 'store';
  if (importPath.startsWith('@/utils/') || importPath.startsWith('../utils/') || importPath.startsWith('./utils/')) return 'utils';
  if (importPath.startsWith('@/workers/') || importPath.startsWith('../workers/') || importPath.startsWith('./workers/')) return 'worker';
  return 'external';
}

function toNodeId(filePath) {
  const relative = path.relative(ROOT, filePath);
  return relative.replace(/[/\\]/g, '-').replace(/\.(tsx|ts|js|jsx|mjs)$/, '');
}

const nodes = [];
const edges = [];
const nodeMap = new Map();

function addNode(id, label, type, layer, filePath, extra = {}) {
  if (nodeMap.has(id)) return;
  const node = { id, label, type, layer, filePath, ...extra };
  nodes.push(node);
  nodeMap.set(id, node);
}

function addEdge(source, target, label, type = 'import') {
  edges.push({ source, target, label, type });
}

addNode('root', '音频修复系统', 'module', 'shared', ROOT);

addNode('frontend', '前端 (React + Vite)', 'module', 'frontend', path.join(ROOT, 'src'));
addNode('backend', '后端 (FastAPI)', 'module', 'backend', path.join(ROOT, 'backend'));
addEdge('root', 'frontend', 'SPA 单页应用', 'data-flow');
addEdge('root', 'backend', 'REST API / WebSocket', 'data-flow');

const pagesDir = path.join(ROOT, 'src', 'pages');
for (const f of safeReaddir(pagesDir)) {
  const fp = path.join(pagesDir, f);
  const code = safeRead(fp);
  const name = f.replace(/\.(tsx|ts)$/, '');
  const pageId = toNodeId(fp);
  addNode(pageId, name, 'page', 'frontend', fp, { children: [] });
  addEdge('frontend', pageId, '路由页面', 'renders');
  if (code) {
    const imports = parseImports(code);
    for (const imp of imports) {
      const resolved = resolveLocalPath(pagesDir, imp);
      if (resolved) {
        const targetId = toNodeId(resolved);
        const impType = classifyImport(imp);
        const label = impType === 'component' ? '渲染' : '使用';
        if (!nodeMap.has(targetId)) {
          const targetName = path.basename(resolved).replace(/\.(tsx|ts|js)$/, '');
          addNode(targetId, targetName, impType, 'frontend', resolved);
        }
        addEdge(pageId, targetId, label, impType === 'component' ? 'renders' : 'import');
        if (nodeMap.get(pageId).children) {
          nodeMap.get(pageId).children.push(targetId);
        }
      }
    }
  }
}

const componentsDir = path.join(ROOT, 'src', 'components');
for (const f of safeReaddir(componentsDir)) {
  const fp = path.join(componentsDir, f);
  const code = safeRead(fp);
  const name = f.replace(/\.(tsx|ts)$/, '');
  const compId = toNodeId(fp);
  if (!nodeMap.has(compId)) {
    addNode(compId, name, 'component', 'frontend', fp);
  }
  if (code) {
    const imports = parseImports(code);
    for (const imp of imports) {
      const resolved = resolveLocalPath(componentsDir, imp);
      if (resolved) {
        const targetId = toNodeId(resolved);
        if (!nodeMap.has(targetId)) {
          const targetName = path.basename(resolved).replace(/\.(tsx|ts|js)$/, '');
          addNode(targetId, targetName, classifyImport(imp), 'frontend', resolved);
        }
        addEdge(compId, targetId, '导入', 'import');
      }
    }
  }
}

const hooksDir = path.join(ROOT, 'src', 'hooks');
for (const f of safeReaddir(hooksDir)) {
  const fp = path.join(hooksDir, f);
  const code = safeRead(fp);
  const name = f.replace(/\.(tsx|ts)$/, '');
  const hookId = toNodeId(fp);
  addNode(hookId, name, 'hook', 'frontend', fp);
  if (code) {
    const imports = parseImports(code);
    for (const imp of imports) {
      const resolved = resolveLocalPath(hooksDir, imp);
      if (resolved) {
        const targetId = toNodeId(resolved);
        if (!nodeMap.has(targetId)) {
          const targetName = path.basename(resolved).replace(/\.(tsx|ts|js)$/, '');
          addNode(targetId, classifyImport(imp), 'frontend', resolved);
        }
        addEdge(hookId, targetId, '调用', 'call');
      }
    }
  }
}

const serviceFile = path.join(ROOT, 'src', 'services', 'backendApi.ts');
const serviceCode = safeRead(serviceFile);
if (serviceCode) {
  addNode(toNodeId(serviceFile), 'backendApi', 'service', 'frontend', serviceFile);
  addEdge('frontend', toNodeId(serviceFile), 'API 服务层', 'import');

  const apiFunctions = [
    'checkFileHash', 'uploadAudio', 'uploadDualAudio',
    'detectAudio', 'detectFile', 'detectByPath',
    'repairAudio', 'repairDualAudio', 'repairDualFromHash',
    'renderAudio', 'waitRenderWithWS',
    'getTaskStatus', 'getTrackStatus', 'getQueueStatus',
    'pollProgress', 'connectProgressWS',
    'getDownloadUrl', 'getPreviewUrl',
    'cancelTask', 'downloadWithProgress',
    'checkBackendHealth', 'fetchAlgorithmVersions', 'fetchDetectorVersions',
    'fetchMemoryInfo', 'fetchStorageEstimate',
    'lookupRepairCache', 'fetchRenderCache',
    'uploadTrainingAudio', 'checkTrainingHash',
    'fetchDeliveryFiles', 'deleteDeliveryFile', 'deleteDeliveryParent',
    'getAudioFiles',
    'mapParamsToBackend', 'mapVocalParamsToBackend', 'mapInstrumentParamsToBackend',
  ];
  for (const fn of apiFunctions) {
    const fnId = `api-${fn}`;
    addNode(fnId, `${fn}()`, 'function', 'frontend', serviceFile);
    addEdge(toNodeId(serviceFile), fnId, '导出函数', 'import');
  }
}

const backendRoutesFile = path.join(ROOT, 'backend', 'api', 'routes.py');
const routesCode = safeRead(backendRoutesFile);
if (routesCode) {
  addNode(toNodeId(backendRoutesFile), 'API Routes', 'module', 'backend', backendRoutesFile);
  addEdge('backend', toNodeId(backendRoutesFile), '路由层', 'import');

  const routeRe = /@router\.(get|post|delete|websocket)\(['"]([^'"]+)['"]/g;
  let rm;
  while ((rm = routeRe.exec(routesCode)) !== null) {
    const method = rm[1].toUpperCase();
    const routePath = rm[2];
    const routeId = `route-${method}-${routePath.replace(/[\/{}]/g, '-')}`;
    addNode(routeId, `${method} ${routePath}`, 'api', 'backend', backendRoutesFile, { description: `${method} ${routePath}` });
    addEdge(toNodeId(backendRoutesFile), routeId, '路由注册', 'data-flow');
  }
}

const taskManagerFile = path.join(ROOT, 'backend', 'services', 'task_manager.py');
const taskManagerCode = safeRead(taskManagerFile);
if (taskManagerCode) {
  addNode(toNodeId(taskManagerFile), 'Task Manager', 'module', 'backend', taskManagerFile);
  addEdge('backend', toNodeId(taskManagerFile), '任务管理', 'import');

  const taskFunctions = [
    { name: 'submit_detect_task', desc: '提交检测任务' },
    { name: '_run_detect', desc: '执行检测（detect_ai_audio）' },
    { name: 'submit_repair_task', desc: '提交修复任务' },
    { name: '_run_repair', desc: '执行修复（repair_audio）' },
  ];
  for (const tf of taskFunctions) {
    const fnId = `tm-${tf.name}`;
    addNode(fnId, tf.name, 'function', 'backend', taskManagerFile, { description: tf.desc });
    addEdge(toNodeId(taskManagerFile), fnId, '任务函数', 'data-flow');
  }

  addEdge('tm-submit_detect_task', 'tm-_run_detect', 'executor.submit', 'call');
  addEdge('tm-submit_repair_task', 'tm-_run_repair', 'executor.submit', 'call');
}

const audioRepairFile = path.join(ROOT, 'backend', 'services', 'audio_repair.py');
const audioRepairCode = safeRead(audioRepairFile);
if (audioRepairCode) {
  addNode(toNodeId(audioRepairFile), 'Audio Repair', 'module', 'backend', audioRepairFile);
  addEdge('backend', toNodeId(audioRepairFile), '修复引擎', 'import');

  const versionRe = /['"](v[\d.]+[a-z]*)['"]\s*:\s*\{/g;
  let vm;
  while ((vm = versionRe.exec(audioRepairCode)) !== null) {
    const ver = vm[1];
    const verId = `algo-${ver}`;
    addNode(verId, `算法 ${ver}`, 'module', 'backend', audioRepairFile, { description: `算法版本 ${ver}` });
    addEdge(toNodeId(audioRepairFile), verId, '算法版本', 'data-flow');
  }
}

const repairServicesDir = path.join(ROOT, 'backend', 'services', 'repair');
for (const f of safeReaddir(repairServicesDir)) {
  const fp = path.join(repairServicesDir, f);
  if (!fs.statSync(fp).isDirectory()) continue;
  const name = f;
  const verId = `repair-module-${name}`;
  addNode(verId, name, 'module', 'backend', fp);
  addEdge(toNodeId(audioRepairFile), verId, '动态加载', 'call');

  const moduleFiles = safeReaddir(fp);
  for (const mf of moduleFiles) {
    if (!mf.endsWith('.py')) continue;
    const mfp = path.join(fp, mf);
    const subName = mf.replace('.py', '');
    if (subName === '__init__' || subName === 'core') continue;
    const subId = `repair-module-${name}-${subName}`;
    addNode(subId, `${name}/${subName}`, 'module', 'backend', mfp);
    addEdge(verId, subId, '子模块', 'import');
  }
}

addNode('dataflow-upload', '上传音频', 'function', 'shared', '', { description: '前端 uploadAudio() → POST /api/v1/upload' });
addNode('dataflow-detect', 'AI 检测', 'function', 'shared', '', { description: '前端 detectAudio() → POST /api/v1/detect → submit_detect_task → _run_detect → detect_ai_audio' });
addNode('dataflow-repair', '音频修复', 'function', 'shared', '', { description: '前端 repairAudio() → POST /api/v1/repair → submit_repair_task → _run_repair → repair_audio' });
addNode('dataflow-render', '渲染交付', 'function', 'shared', '', { description: '前端 renderAudio() → POST /api/v1/render → _run_render → render_output' });
addNode('dataflow-download', '下载结果', 'function', 'shared', '', { description: '前端 getDownloadUrl() → GET /api/v1/download/{task_id}' });
addNode('dataflow-ws', 'WebSocket 进度', 'function', 'shared', '', { description: '前端 connectProgressWS() → WS /api/v1/ws/{task_id}' });

addEdge('dataflow-upload', 'dataflow-detect', '检测', 'data-flow');
addEdge('dataflow-detect', 'dataflow-repair', '修复', 'data-flow');
addEdge('dataflow-repair', 'dataflow-render', '渲染', 'data-flow');
addEdge('dataflow-render', 'dataflow-download', '下载', 'data-flow');
addEdge('dataflow-ws', 'dataflow-detect', '进度推送', 'data-flow');
addEdge('dataflow-ws', 'dataflow-repair', '进度推送', 'data-flow');
addEdge('dataflow-ws', 'dataflow-render', '进度推送', 'data-flow');

addNode('dataflow-upload-dual', '双轨上传', 'function', 'shared', '', { description: '前端 uploadDualAudio() → POST /api/v1/upload-dual' });
addNode('dataflow-repair-dual', '双轨修复', 'function', 'shared', '', { description: '前端 repairDualAudio() → POST /api/v1/repair-dual → 人声+伴奏分别修复后混音' });
addEdge('dataflow-upload-dual', 'dataflow-repair-dual', '双轨修复', 'data-flow');
addEdge('dataflow-repair-dual', 'dataflow-render', '渲染交付', 'data-flow');

const flowData = { nodes, edges };

const publicDir = path.join(ROOT, 'public');
if (!fs.existsSync(publicDir)) {
  fs.mkdirSync(publicDir, { recursive: true });
}

fs.writeFileSync(path.join(publicDir, 'flow-data.json'), JSON.stringify(flowData, null, 2), 'utf-8');
console.log(`[analyze-flow] 完成: ${nodes.length} 个节点, ${edges.length} 条边`);
console.log(`[analyze-flow] 输出: public/flow-data.json`);