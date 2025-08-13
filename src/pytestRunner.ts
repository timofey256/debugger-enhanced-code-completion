import * as vscode from 'vscode';
import { spawn } from 'child_process';
import * as path from 'path';

export async function runPytest(
  controller: vscode.TestController,
  run: vscode.TestRun,
  request: vscode.TestRunRequest,
  token: vscode.CancellationToken
) {
  const ws = vscode.workspace.workspaceFolders?.[0];
  if (!ws) return;
  const cwd = ws.uri.fsPath;
  const pytest = vscode.workspace.getConfiguration('pytestSmartDebugger').get<string>('pytestPath') ?? 'pytest';
  const extra = vscode.workspace.getConfiguration('pytestSmartDebugger').get<string[]>('pytestArgs') ?? ['-q', '-s'];

  const targets = request.include ?? collectAll(controller);
  for (const item of targets) run.enqueued(item);

  // Build nodeids
  const nodeids = targets
    .filter(t => t.children.size === 0) // leaves only
    .map(t => t.id);

  const isRunAll = !request.include || request.include.length === 0;
  const args = isRunAll ? [...extra] : [...extra, ...nodeids];
  const cp = spawn(pytest, args, { cwd, shell: true });
  let out = ''; let err = '';
  cp.stdout.on('data', d => out += d.toString());
  cp.stderr.on('data', d => err += d.toString());

  await new Promise((res) => cp.on('close', res));
  console.log("Finished pytest run. Analysing...");
  console.log(`Result out: ${out}`);
  console.log(`Result err: ${err}`);

  // Very lightweight parsing: mark passed tests whose nodeid appear with " . " and failed with "F"/traceback.
  // For real robustness, recommend enabling pytest-json-report and parsing its JSON.
  const failedIds = new Set<string>();
  for (const item of targets) {
    if (out.includes(item.id) && /FAILED/.test(out)) { /* coarse */ }
  }

  const combined = out + '\n' + err;
  const failedIn = (nodeid: string) => {
    const escaped = nodeid.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const re = new RegExp(`(?:^|\\n)(?:FAILED|ERROR)\\s+${escaped}(?:\\b|\\s|$)`);
    const reRev = new RegExp(`${escaped}\\s+(?:FAILED|ERROR)(?:\\b|\\s|$)`);
    return re.test(combined) || reRev.test(combined);
  };

  // Minimal heuristic: if output contains "<nodeid> FAILED"
  for (const item of targets) {
    run.started(item);
    const failed = failedIn(item.id);
    if (failed) {
      const loc = new vscode.Location(item.uri!, new vscode.Position(0,0));
      const msg = new vscode.TestMessage('Test failed.\n' + extractFailureFor(item.id, out, err));
      msg.location = loc;
      run.failed(item, msg);
      (item as any).lastRunState = 'failed';
    } else {
      run.passed(item, 1);
      (item as any).lastRunState = 'passed';
    }
  }
}

export async function runSingleTest(controller: vscode.TestController, item: vscode.TestItem) {
  const ws = vscode.workspace.workspaceFolders?.[0];
  if (!ws) return;
  const cwd = ws.uri.fsPath;
  const pytest = vscode.workspace.getConfiguration('pytestSmartDebugger').get<string>('pytestPath') ?? 'pytest';
  const extra = vscode.workspace.getConfiguration('pytestSmartDebugger').get<string[]>('pytestArgs') ?? ['-q'];

  const run = controller.createTestRun(new vscode.TestRunRequest([item]));
  run.enqueued(item);
  run.started(item);

  const cp = spawn(pytest, [...extra, item.id], { cwd, shell: true });
  let out = ''; let err = '';
  cp.stdout.on('data', d => out += d.toString());
  cp.stderr.on('data', d => err += d.toString());
  await new Promise((res) => cp.on('close', res));

  const combined = out + '\n' + err;
  const escaped = item.id.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const re = new RegExp(`(?:^|\\n)(?:FAILED|ERROR)\\s+${escaped}(?:\\b|\\s|$)`);
  const reRev = new RegExp(`${escaped}\\s+(?:FAILED|ERROR)(?:\\b|\\s|$)`);
  const failed = re.test(combined) || reRev.test(combined);
  if (failed) {
    const loc = new vscode.Location(item.uri!, new vscode.Position(0,0));
    const msg = new vscode.TestMessage('Test failed.\n' + extractFailureFor(item.id, out, err));
    msg.location = loc;
    run.failed(item, msg);
    (item as any).lastRunState = 'failed';
  } else {
    run.passed(item, 1);
    (item as any).lastRunState = 'passed';
  }
  run.end();
}

function collectAll(controller: vscode.TestController) {
  const items: vscode.TestItem[] = [];
  controller.items.forEach(i => gather(i, items));
  return items;
}
function gather(item: vscode.TestItem, acc: vscode.TestItem[]) {
  if (item.children.size === 0) acc.push(item);
  item.children.forEach(c => gather(c, acc));
}
function extractFailureFor(id: string, out: string, err: string) {
  const text = out + '\n' + err;
  const idx = text.indexOf(id);
  if (idx < 0) return text.slice(-2000);
  return text.slice(idx, idx + 4000);
}
