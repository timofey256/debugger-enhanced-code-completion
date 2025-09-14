import * as vscode from 'vscode';
import * as path from 'path';
import { discoverTests } from './testDiscovery';
import { runPytest, runSingleTest } from './pytestRunner';
import { ensureServerAndRequest } from './server';
import { showDiffWebview } from './diffWebview';
import { applyPatchesFromResponse } from './patch';
import { buildUnifiedDiff, PatchResponse } from './patchFormat';
import { spawn } from 'child_process';

let controller: vscode.TestController;
let serverProcess: ReturnType<typeof spawn> | undefined;

export async function activate(ctx: vscode.ExtensionContext) {
// Leaving this here - perhaps we will be starting the server automathically
//
//  console.log(`extensionPath = ${ctx.extensionPath}`);
//  const serverScript = path.join(ctx.extensionPath, 'backend', 'server.py');
//  serverProcess = spawn('python', [serverScript], {
//        cwd: path.dirname(serverScript),
//        env: { ...process.env, PORT: '5000' } // example: pass environment vars
//  });
//  serverProcess.stdout?.on('data', data => {
//      console.log(`Server: ${data}`);
//  });
//  
//  serverProcess.stderr?.on('data', data => {
//      console.error(`Server error: ${data}`);
//  });
//  
//  serverProcess.on('close', code => {
//      console.log(`Server exited with code ${code}`);
//  });

  // --- Define all the commands ---
  controller = vscode.tests.createTestController('pytestSmartDebugger.controller', 'Pytest');
  ctx.subscriptions.push(controller);

  const status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left);
  status.name = "Pytest Smart Debugger";
  status.text = "Pytest: idle";
  status.tooltip = "Pytest Smart Debugger";
  status.show();
  ctx.subscriptions.push(status);

  controller.refreshHandler = async (_token?: vscode.CancellationToken) => {
    status.text = "Pytest: Loading tests…";
    try {
      controller.items.replace([]);
      await discoverTests(controller);
      status.text = "Pytest: Ready";
    } catch (e) {
      status.text = "Pytest: Error";
      vscode.window.showErrorMessage("Failed to load tests");
    }
  };

  controller.createRunProfile(
    'Run',
    vscode.TestRunProfileKind.Run,
    async (request, token) => {
      status.text = "Pytest: running tests...";
      const run = controller.createTestRun(request);
      try {
        await runPytest(controller, run, request, token);
      } finally {
        run.end();
        status.text = "Pytest: tests are ready"; 
      }
    },
    true
  );

  ctx.subscriptions.push(
    vscode.commands.registerCommand('pytestSmartDebugger.runAll', async () => {
      await vscode.commands.executeCommand('testing.runAll');
    }),
    vscode.commands.registerCommand('pytestSmartDebugger.tryDebug', async (testItem?: vscode.TestItem) => {
      const item = testItem ?? await pickFailedTest(controller);
      console.log(`item: ${JSON.stringify(item, null, 2)}`);
      if (!item) { return; }
      const workspace = vscode.workspace.workspaceFolders?.[0];
      if (!workspace) { return; }

      const failure = (item as any).lastFailureMessage ?? 'No failure details found.';
      const payload = {
        testId: item.id,
        file: item.uri?.fsPath,
        failure
      };

      console.log("payload:", JSON.stringify(payload, null, 2));
      const reply = await vscode.window.withProgress(
        {
          location: vscode.ProgressLocation.Notification,
          title: "Proposing a patch…",
          cancellable: false,
        },
        async (progress) => {
          progress.report({ message: "Contacting local server…" });
          const r = await ensureServerAndRequest(payload);
          progress.report({ message: "Preparing diff preview…" });
          return r;
        }
      );
      console.log(`Reply : ${JSON.stringify(reply, null, 2)}`);
      if (!reply) return;

      let unifiedDiff: string | undefined;
      let structured: PatchResponse | undefined;
      
      if (reply.kind === 'diff') {
        unifiedDiff = reply.diff;
      } else if (reply.kind === 'both') {
        structured = reply.data;
        const root = structured.project_root;
        const patches = structured.patches ?? [];
        unifiedDiff = buildUnifiedDiff(root, patches);
      }

      if (!unifiedDiff || !unifiedDiff.trim().startsWith('diff')) {
        vscode.window.showWarningMessage('No diff produced by server.');
        return;
      }

      await showDiffWebview(ctx, unifiedDiff, async () => {
        if (!structured || !structured.patches?.length) {
          vscode.window.showErrorMessage('No structured patches available from server to apply.');
          return false;
        }
        const applied = await applyPatchesFromResponse(structured);
        if (!applied) {
          vscode.window.showErrorMessage('Failed to apply patch.');
          return false;
        }
        await runSingleTest(controller, item);
        return true;
      });
    })
  );

  status.text = "Pytest: Loading tests…";
  try {
    controller.items.replace([]);
    await discoverTests(controller);
    status.text = "Pytest: Ready";
  } catch {
    status.text = "Pytest: Error";
  }

  const ws = vscode.workspace.workspaceFolders?.[0];
  if (ws) {
    const watcher = vscode.workspace.createFileSystemWatcher(
      new vscode.RelativePattern(ws, "**/*{test,tests}*.py")
    );
    const doRefresh = async () => {
      status.text = "Pytest: Loading tests…";
      try {
        controller.items.replace([]);
        await discoverTests(controller);
        status.text = "Pytest: Ready";
      } catch {
        status.text = "Pytest: Error";
      }
    };
    watcher.onDidChange(doRefresh);
    watcher.onDidCreate(doRefresh);
    watcher.onDidDelete(doRefresh);
    ctx.subscriptions.push(watcher);
  }
}

export function deactivate() {
    if (serverProcess) {
        serverProcess.kill();
    }
}

async function pickFailedTest(controller: vscode.TestController) {
  const failed: vscode.TestItem[] = [];
  controller.items.forEach(item => collectFailed(item, failed));

  if (!failed.length) {
    vscode.window.showInformationMessage('No failed tests to debug.');
    return;
  }

  const pick = await vscode.window.showQuickPick(
    failed.map(f => ({ label: f.label, description: f.id, item: f }))
  );
  return pick?.item;
}

function collectFailed(item: vscode.TestItem, acc: vscode.TestItem[]) {
  const state = (item as any).lastRunState as 'passed'|'failed'|'unknown'|undefined;
  if (state === 'failed') acc.push(item);
  item.children.forEach(child => collectFailed(child, acc));
}

