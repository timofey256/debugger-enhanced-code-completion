import * as vscode from 'vscode';
import { spawn } from 'child_process';
import * as os from 'os';
import * as fs from 'fs/promises';
import * as path from 'path';

export async function applyUnifiedDiff(diff: string): Promise<boolean> {
  const cfg = vscode.workspace.getConfiguration('pytestSmartDebugger');
  const useGit = cfg.get<boolean>('useGitApply') ?? true;
  const ws = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  if (!ws) return false;

  const tmp = path.join(os.tmpdir(), 'pytest-smart-debugger.patch');
  await fs.writeFile(tmp, diff, 'utf8');

  if (useGit) {
    const ok = await exec('git', ['apply', '--unsafe-paths', '--reject', '--whitespace=fix', tmp], ws);
    if (ok) return true;
  }

  // Fallback: naive apply (only supports simple hunks); production: use a proper diff library.
  vscode.window.showWarningMessage('Falling back to naive patch application (may fail on complex hunks).');
  return await naiveApply(ws, diff);
}

function exec(cmd: string, args: string[], cwd: string) {
  return new Promise<boolean>(res => {
    const p = spawn(cmd, args, { cwd, shell: true });
    p.on('close', code => res(code === 0));
  });
}

async function naiveApply(root: string, diff: string): Promise<boolean> {
  // Extremely simplified: only handles patches with full file context and no renames.
  try {
    const files = parseFilesFromDiff(diff);
    for (const f of files) {
      const full = path.join(root, f.path);
      await fs.writeFile(full, f.content, 'utf8');
    }
    return true;
  } catch {
    return false;
  }
}

function parseFilesFromDiff(_diff: string): { path: string, content: string }[] {
  // Placeholder (intentionally minimal); replace with real parser if you skip git.
  throw new Error('Naive parser not implemented');
}

