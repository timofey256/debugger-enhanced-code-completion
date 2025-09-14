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
exports.activate = activate;
exports.deactivate = deactivate;
const vscode = __importStar(require("vscode"));
const testDiscovery_1 = require("./testDiscovery");
const pytestRunner_1 = require("./pytestRunner");
const server_1 = require("./server");
const diffWebview_1 = require("./diffWebview");
const patch_1 = require("./patch");
const patchFormat_1 = require("./patchFormat");
let controller;
let serverProcess;
async function activate(ctx) {
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
    controller.refreshHandler = async (_token) => {
        status.text = "Pytest: Loading tests…";
        try {
            controller.items.replace([]);
            await (0, testDiscovery_1.discoverTests)(controller);
            status.text = "Pytest: Ready";
        }
        catch (e) {
            status.text = "Pytest: Error";
            vscode.window.showErrorMessage("Failed to load tests");
        }
    };
    controller.createRunProfile('Run', vscode.TestRunProfileKind.Run, async (request, token) => {
        status.text = "Pytest: running tests...";
        const run = controller.createTestRun(request);
        try {
            await (0, pytestRunner_1.runPytest)(controller, run, request, token);
        }
        finally {
            run.end();
            status.text = "Pytest: tests are ready";
        }
    }, true);
    ctx.subscriptions.push(vscode.commands.registerCommand('pytestSmartDebugger.runAll', async () => {
        await vscode.commands.executeCommand('testing.runAll');
    }), vscode.commands.registerCommand('pytestSmartDebugger.tryDebug', async (testItem) => {
        const item = testItem ?? await pickFailedTest(controller);
        console.log(`item: ${JSON.stringify(item, null, 2)}`);
        if (!item) {
            return;
        }
        const workspace = vscode.workspace.workspaceFolders?.[0];
        if (!workspace) {
            return;
        }
        const failure = item.lastFailureMessage ?? 'No failure details found.';
        const payload = {
            testId: item.id,
            file: item.uri?.fsPath,
            failure
        };
        console.log("payload:", JSON.stringify(payload, null, 2));
        const reply = await vscode.window.withProgress({
            location: vscode.ProgressLocation.Notification,
            title: "Proposing a patch…",
            cancellable: false,
        }, async (progress) => {
            progress.report({ message: "Contacting local server…" });
            const r = await (0, server_1.ensureServerAndRequest)(payload);
            progress.report({ message: "Preparing diff preview…" });
            return r;
        });
        console.log(`Reply : ${JSON.stringify(reply, null, 2)}`);
        if (!reply)
            return;
        let unifiedDiff;
        let structured;
        if (reply.kind === 'diff') {
            unifiedDiff = reply.diff;
        }
        else if (reply.kind === 'both') {
            structured = reply.data;
            const root = structured.project_root;
            const patches = structured.patches ?? [];
            unifiedDiff = (0, patchFormat_1.buildUnifiedDiff)(root, patches);
        }
        if (!unifiedDiff || !unifiedDiff.trim().startsWith('diff')) {
            vscode.window.showWarningMessage('No diff produced by server.');
            return;
        }
        await (0, diffWebview_1.showDiffWebview)(ctx, unifiedDiff, async () => {
            if (!structured || !structured.patches?.length) {
                vscode.window.showErrorMessage('No structured patches available from server to apply.');
                return false;
            }
            const applied = await (0, patch_1.applyPatchesFromResponse)(structured);
            if (!applied) {
                vscode.window.showErrorMessage('Failed to apply patch.');
                return false;
            }
            await (0, pytestRunner_1.runSingleTest)(controller, item);
            return true;
        });
    }));
    status.text = "Pytest: Loading tests…";
    try {
        controller.items.replace([]);
        await (0, testDiscovery_1.discoverTests)(controller);
        status.text = "Pytest: Ready";
    }
    catch {
        status.text = "Pytest: Error";
    }
    const ws = vscode.workspace.workspaceFolders?.[0];
    if (ws) {
        const watcher = vscode.workspace.createFileSystemWatcher(new vscode.RelativePattern(ws, "**/*{test,tests}*.py"));
        const doRefresh = async () => {
            status.text = "Pytest: Loading tests…";
            try {
                controller.items.replace([]);
                await (0, testDiscovery_1.discoverTests)(controller);
                status.text = "Pytest: Ready";
            }
            catch {
                status.text = "Pytest: Error";
            }
        };
        watcher.onDidChange(doRefresh);
        watcher.onDidCreate(doRefresh);
        watcher.onDidDelete(doRefresh);
        ctx.subscriptions.push(watcher);
    }
}
function deactivate() {
    if (serverProcess) {
        serverProcess.kill();
    }
}
async function pickFailedTest(controller) {
    const failed = [];
    controller.items.forEach(item => collectFailed(item, failed));
    if (!failed.length) {
        vscode.window.showInformationMessage('No failed tests to debug.');
        return;
    }
    const pick = await vscode.window.showQuickPick(failed.map(f => ({ label: f.label, description: f.id, item: f })));
    return pick?.item;
}
function collectFailed(item, acc) {
    const state = item.lastRunState;
    if (state === 'failed')
        acc.push(item);
    item.children.forEach(child => collectFailed(child, acc));
}
//# sourceMappingURL=extension.js.map