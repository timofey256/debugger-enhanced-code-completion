import * as vscode from 'vscode';
import { spawn } from 'child_process';
import * as path from 'path';

export async function discoverTests(controller: vscode.TestController) {
  const ws = vscode.workspace.workspaceFolders?.[0];
  if (!ws) return;
  const cwd = ws.uri.fsPath;
  const pytest = vscode.workspace.getConfiguration('pytestSmartDebugger').get<string>('pytestPath') ?? 'pytest';

  const cp = spawn(pytest, ['--collect-only', '-q'], { cwd, shell: true });
  const chunks: string[] = [];
  cp.stdout.on('data', d => chunks.push(d.toString()));
  await new Promise((res) => cp.on('close', res));
  const lines = chunks.join('').split('\n').map(l => l.trim()).filter(Boolean);

  for (const node of lines) {
    if (node.startsWith('<') || node.includes('no tests')) continue;
    const [file, ...rest] = node.split('::');
    const fileUri = vscode.Uri.file(path.join(cwd, file));
    let fileItem = controller.items.get(fileUri.toString());
    if (!fileItem) {
      fileItem = controller.createTestItem(fileUri.toString(), file, fileUri);
      controller.items.add(fileItem);
    }
    const id = node;
    const label = rest.join('::') || file;
    const testItem = controller.createTestItem(id, label, fileUri);
    fileItem.children.add(testItem);
  }
}
