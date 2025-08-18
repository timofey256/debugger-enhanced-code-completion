import * as vscode from 'vscode';
import { spawn } from 'child_process';

type FailuresMap = Map<string, string>;

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

  const nodeids = targets
    .filter(t => t.children.size === 0)
    .map(t => t.id);

  const isRunAll = !request.include || request.include.length === 0;
  const args = isRunAll ? [...extra] : [...extra, ...nodeids];
  const cp = spawn(pytest, args, { cwd, shell: true });
  let out = ''; let err = '';
  cp.stdout.on('data', d => out += d.toString());
  cp.stderr.on('data', d => err += d.toString());

  const full = out + '\n' + err;
  const failures = parseFailuresSection(full);          
  const summaryFailed = parseSummaryFailedNodeids(full);
  console.log("Finished pytest run. Analysing...");
  console.log(`Result out: ${out}`);
  console.log(`Result err: ${err}`);

  for (const item of targets) {
    if (out.includes(item.id) && /FAILED/.test(out)) { /* coarse */ }
  }

  for (const item of targets) {
    run.started(item);
    const headerKey = nodeidToFailuresHeader(item.id);
    const block = headerKey ? failures.get(headerKey) : undefined;
    let failed = false;
    let message: string | undefined = undefined;

    if (block) {
      failed = true;
      message = block.trim();
    } else if (summaryFailed.has(item.id)) {
      failed = true;
      message = 'Test failed (see output).';
    } else {
      failed = false;
    }

    if (failed) {
      const loc = bestFailureLocation(block, item);
      const msgObj = new vscode.TestMessage(message ?? 'Test failed.');
      if (loc) msgObj.location = loc;
      run.failed(item, msgObj);
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
  const exitCode: number = await new Promise((res) => cp.on('close', (code) => res(code ?? 0)));

  const failed = exitCode !== 0;
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


/**
 * Convert a pytest nodeid into a FAILURES header key.
 * Examples:
 *  - "path/to/test_cli.py::TestCLIIntegration::test_license" -> "TestCLIIntegration.test_license"
 *  - "path/to/test_mod.py::test_standalone" -> "test_standalone"
 *  - Parametrized: keep the bracket suffix, e.g. "test_foo[param]" -> "test_foo[param]"
 */
function nodeidToFailuresHeader(nodeid: string): string | undefined {
  const parts = nodeid.split('::');
  if (parts.length === 0) return undefined;
  if (parts.length === 1) {
    return undefined;
  }
  if (parts.length >= 3) {
    const cls = parts[parts.length - 2];
    const test = parts[parts.length - 1];
    return `${cls}.${test}`;
  }
  return parts[parts.length - 1];
}

/**
 * Parse the FAILURES section emitted by pytest and return a map:
 *   header ("Class.test" or "test_function") -> full traceback block
 *
 * We look for:
 *   ^={10,} FAILURES ={10,}$       (section start)
 *   ^_{10,}\s+(.*?)\s+_{10,}$      (per-failure header with name we key by)
 * and capture text until the next header or the next big ==== SECTION ==== line.
 */
function parseFailuresSection(text: string): FailuresMap {
  const map: FailuresMap = new Map();
  const lines = text.split(/\r?\n/);

  // start of FAILURES section
  const isEqHeader = (s: string) => /^=+\s*[A-Z ]+\s*=+$/.test(s);
  let start = -1;
  for (let i = 0; i < lines.length; i++) {
    if (/^=+\s*FAILURES\s*=+$/.test(lines[i])) { start = i + 1; break; }
  }
  if (start === -1) return map; // no failures section found

  // find end of FAILURES section: next ========== SECTION ========== or EOF
  let end = lines.length;
  for (let i = start; i < lines.length; i++) {
    if (isEqHeader(lines[i]) && !/^=+\s*FAILURES\s*=+$/.test(lines[i])) {
      end = i; break;
    }
  }

  const headerRegex = /^_{5,}\s+(.*?)\s+_{5,}$/; // "_____ <name> _____"
  let i = start;
  while (i < end) {
    const headerLine = lines[i];
    const m = headerRegex.exec(headerLine);
    if (!m) { i++; continue; }
    const headerName = (m[1] || '').trim();
    const blockStart = i + 1;
    let j = blockStart;
    while (j < end && !headerRegex.test(lines[j])) j++;
    const block = lines.slice(blockStart, j).join('\n');
    if (headerName) {
      map.set(headerName, block);
    }
    i = j;
  }
  return map;
}

function parseSummaryFailedNodeids(text: string): Set<string> {
  const set = new Set<string>();
  const re = /^(FAILED|ERROR)\s+(\S+?)(\s+-\s+.*)?$/gm;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    const nodeid = m[2];
    if (nodeid) set.add(nodeid);
  }
  return set;
}

function bestFailureLocation(block: string | undefined, item: vscode.TestItem): vscode.Location | undefined {
  if (!block || !item.uri) return undefined;
  const m = /([^\s:]+\.py):(\d+):/.exec(block);
  if (m) {
    const line = Math.max(0, parseInt(m[2], 10) - 1);
    return new vscode.Location(item.uri, new vscode.Position(line, 0));
  }
  return new vscode.Location(item.uri, new vscode.Position(0, 0));
}

