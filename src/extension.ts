import * as vscode from 'vscode';
import { discoverTests } from './testDiscovery';
import { runPytest, runSingleTest } from './pytestRunner';
import { ensureServerAndRequest } from './server';
import { showDiffWebview } from './diffWebview';
import { applyPatchesFromResponse } from './patch';
import { buildUnifiedDiff, PatchResponse } from './patchFormat';

let controller: vscode.TestController;

export async function activate(ctx: vscode.ExtensionContext) {
  controller = vscode.tests.createTestController('pytestSmartDebugger.controller', 'Pytest');
  ctx.subscriptions.push(controller);

  controller.refreshHandler = async (_token?: vscode.CancellationToken) => {
    controller.items.replace([]);
    await discoverTests(controller);
  };

  controller.createRunProfile(
    'Run',
    vscode.TestRunProfileKind.Run,
    async (request, token) => {
      const run = controller.createTestRun(request);
      try {
        await runPytest(controller, run, request, token);
      } finally {
        run.end();
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
      if (!item) { return; }
      const workspace = vscode.workspace.workspaceFolders?.[0];
      if (!workspace) { return; }

      const failure = item.error ?? 'No failure details found.';
      const payload = {
        testId: item.id,
        file: item.uri?.fsPath,
        failure
      };

      const reply = await ensureServerAndRequest(payload);
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

  controller.items.replace([]);
  await discoverTests(controller);

  // watch for test file changes to auto-refresh
  const ws = vscode.workspace.workspaceFolders?.[0];
  if (ws) {
    const watcher = vscode.workspace.createFileSystemWatcher(
      new vscode.RelativePattern(ws, "**/*{test,tests}*.py")
    );
    watcher.onDidChange(async () => {
      controller.items.replace([]);
      await discoverTests(controller);
    });
    watcher.onDidCreate(async () => {
      controller.items.replace([]);
      await discoverTests(controller);
    });
    watcher.onDidDelete(async () => {
      controller.items.replace([]);
      await discoverTests(controller);
    });
    ctx.subscriptions.push(watcher);
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

