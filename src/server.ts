import * as vscode from 'vscode';
import { spawn } from 'child_process';
import * as http from 'http';
import { PatchResponse } from './patchFormat';

let proc: import('child_process').ChildProcess | undefined;

export type ServerReply =
  | { kind: 'diff', diff: string } 
  | { kind: 'both', data: PatchResponse, diff?: string };

export async function ensureServerAndRequest(payload: any): Promise<ServerReply | undefined> {
  const cfg = vscode.workspace.getConfiguration('pytestSmartDebugger');
  const port = cfg.get<number>('serverPort') ?? 5123;
  const auto = cfg.get<boolean>('autoStartServer') ?? true;

  // Probe
  const alive = await isAlive(port);
  if (!alive && auto) {
    await startServer();
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

function postJson(url: string, data: any): Promise<ServerReply> {
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
      const ctype = res.headers['content-type'] || '';
      res.on('data', c => chunks.push(c as Buffer));
      res.on('end', () => {
        const buf = Buffer.concat(chunks);
        const text = buf.toString('utf8');

        if (ctype.includes('application/json')) {
          const json = JSON.parse(text) as PatchResponse;
          resolve({ kind: 'both', data: json, diff: json.unified_diff });
        } else {
          if (text.trim().startsWith('diff')) {
            resolve({ kind: 'diff', diff: text });
          } else {
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

