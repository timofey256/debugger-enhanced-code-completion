import * as vscode from 'vscode';
import { spawn } from 'child_process';
import * as http from 'http';

let proc: import('child_process').ChildProcess | undefined;

export async function ensureServerAndRequest(payload: any): Promise<string | undefined> {
  const cfg = vscode.workspace.getConfiguration('pytestSmartDebugger');
  const port = cfg.get<number>('serverPort') ?? 5123;
  const auto = cfg.get<boolean>('autoStartServer') ?? true;

  // Probe the port
  const alive = await isAlive(port);
  if (!alive && auto) {
    await startServer();
    // Wait briefly then probe again
    await new Promise(r => setTimeout(r, 800));
  }
  const ok = await isAlive(port);
  if (!ok) {
    vscode.window.showErrorMessage(`Python server not reachable on port ${port}.`);
    return;
  }
  return postJson(`http://127.0.0.1:${port}/debug`, payload);
}

async function startServer() {
  if (proc && !proc.killed) return;
  const cfg = vscode.workspace.getConfiguration('pytestSmartDebugger');
  const python = cfg.get<string>('pythonPath') ?? 'python';
  const script = cfg.get<string>('serverCommand')!;
  const ws = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;

  proc = spawn(python, [script], { cwd: ws, shell: true });
  proc.stdout?.on('data', d => console.log('[server]', d.toString()));
  proc.stderr?.on('data', d => console.error('[server-err]', d.toString()));
}

function isAlive(port: number): Promise<boolean> {
  return new Promise(res => {
    const req = http.request({ method: 'GET', host: '127.0.0.1', port, path: '/health', timeout: 400 }, r => {
      res(r.statusCode === 200);
    });
    req.on('timeout', () => { req.destroy(); res(false); });
    req.on('error', () => res(false));
    req.end();
  });
}

function postJson(url: string, data: any): Promise<string> {
  return new Promise((resolve, reject) => {
    const u = new URL(url);
    const req = http.request({
      method: 'POST',
      hostname: u.hostname,
      port: Number(u.port),
      path: u.pathname,
      headers: { 'Content-Type': 'application/json' }
    }, res => {
      const chunks: Buffer[] = [];
      res.on('data', c => chunks.push(c as Buffer));
      res.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
    });
    req.on('error', reject);
    req.write(JSON.stringify(data));
    req.end();
  });
}
