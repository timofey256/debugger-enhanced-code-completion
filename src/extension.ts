import * as vscode from 'vscode';
import { discoverTests } from './testDiscovery';
import { runPytest, runSingleTest } from './pytestRunner';
import { ensureServerAndRequest } from './server';
import { showDiffWebview } from './diffWebview';
import { applyUnifiedDiff } from './patch';

let controller: vscode.TestController;

export async function activate(ctx: vscode.ExtensionContext) {
  controller = vscode.tests.createTestController('pytestSmartDebugger.controller', 'Pytest');
  ctx.subscriptions.push(controller);

  // Test discovery
  controller.refreshHandler = async () => {
    controller.items.replace([]);
    await discoverTests(controller);
  };

  // Run profile
  controller.createRunProfile(
    'Run',
    vscode.TestRunProfileKind.Run,
    async (request, token) => {
      const run = controller.createTestRun(request);
      try {
        console.log("Starting the pytest runner...");
        await runPytest(controller, run, request, token);
      } finally {
        run.end();
      }
    },
    true
  );

  // Commands
  ctx.subscriptions.push(
    vscode.commands.registerCommand('pytestSmartDebugger.runAll', async () => {
      await vscode.commands.executeCommand('testing.runAll');
    }),
    vscode.commands.registerCommand('pytestSmartDebugger.tryDebug', async (testItem?: vscode.TestItem) => {
      const item = testItem ?? await pickFailedTest(controller);
      if (!item) { return; }
      const workspace = vscode.workspace.workspaceFolders?.[0];
      if (!workspace) { return; }

      // Gather failure context (stdout/stderr) from last run if available
      const failure = item.error ?? 'No failure details found.';
      const payload = {
        testId: item.id,
        file: item.uri?.fsPath,
        failure
      };

      const diff = await ensureServerAndRequest(payload);
      if (!diff || !diff.trim().startsWith('diff')) {
        vscode.window.showWarningMessage('No diff produced by server.');
        return;
      }
      await showDiffWebview(ctx, diff, async () => {
        const applied = await applyUnifiedDiff(diff);
        if (!applied) {
          vscode.window.showErrorMessage('Failed to apply patch.');
          return false;
        }
        // Rerun just this test
        await runSingleTest(controller, item);
        return true;
      });
    })
  );

  // Initial discovery
  const cts = new vscode.CancellationTokenSource();
  try {
    await controller.refreshHandler?.(cts.token);
  } finally {
    cts.dispose();
  }
}

export function deactivate() {}
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

