"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.ensureServerAndRequest = ensureServerAndRequest;
const vscode = __importStar(require("vscode"));
const child_process_1 = require("child_process");
const http = __importStar(require("http"));
let proc;
async function ensureServerAndRequest(payload) {
    const cfg = vscode.workspace.getConfiguration('pytestSmartDebugger');
    const port = cfg.get('serverPort') ?? 5123;
    const auto = cfg.get('autoStartServer') ?? true;
    // Probe
    const alive = await isAlive(port);
    if (!alive && auto) {
        console.log(`Server is not alive on port ${port}`);
    }
    const ok = await isAlive(port);
    if (!ok) {
        vscode.window.showErrorMessage(`Python server not reachable on port ${port}.`);
        return;
    }
    return postJson(`http://127.0.0.1:${port}/debug`, payload);
}
async function startServer() {
    if (proc && !proc.killed)
        return;
    const cfg = vscode.workspace.getConfiguration('pytestSmartDebugger');
    const python = cfg.get('pythonPath') ?? 'python';
    const script = cfg.get('serverCommand');
    const ws = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
    proc = (0, child_process_1.spawn)(python, [script], { cwd: ws, shell: true });
    proc.stdout?.on('data', d => console.log('[server]', d.toString()));
    proc.stderr?.on('data', d => console.error('[server-err]', d.toString()));
}
function isAlive(port) {
    return new Promise(res => {
        const req = http.request({ method: 'GET', host: '127.0.0.1', port, path: '/health', timeout: 400 }, r => {
            res(r.statusCode === 200);
        });
        req.on('timeout', () => { req.destroy(); res(false); });
        req.on('error', () => res(false));
        req.end();
    });
}
function postJson(url, data) {
    return new Promise((resolve, reject) => {
        const u = new URL(url);
        const req = http.request({
            method: 'POST',
            hostname: u.hostname,
            port: Number(u.port),
            path: u.pathname,
            headers: { 'Content-Type': 'application/json' }
        }, res => {
            const chunks = [];
            const ctype = res.headers['content-type'] || '';
            res.on('data', c => chunks.push(c));
            res.on('end', () => {
                const buf = Buffer.concat(chunks);
                const text = buf.toString('utf8');
                if (ctype.includes('application/json')) {
                    const json = JSON.parse(text);
                    resolve({ kind: 'both', data: json, diff: json.unified_diff });
                }
                else {
                    if (text.trim().startsWith('diff')) {
                        resolve({ kind: 'diff', diff: text });
                    }
                    else {
                        reject(new Error('Unexpected server response'));
                    }
                }
            });
        });
        req.on('error', reject);
        req.write(JSON.stringify(data));
        req.end();
    });
}
//# sourceMappingURL=server.js.map