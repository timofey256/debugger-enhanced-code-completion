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
exports.showDiffWebview = showDiffWebview;
const vscode = __importStar(require("vscode"));
async function showDiffWebview(ctx, diff, onApply) {
    const panel = vscode.window.createWebviewPanel('pytestSmartDebugger.diff', 'Suggested Fix (unified diff)', vscode.ViewColumn.Active, { enableScripts: true, retainContextWhenHidden: false });
    panel.webview.html = render(diff);
    panel.webview.onDidReceiveMessage(async (msg) => {
        if (msg.type === 'apply') {
            const ok = await onApply();
            if (ok)
                panel.dispose();
        }
        else if (msg.type === 'dismiss') {
            panel.dispose();
        }
    });
}
function render(diff) {
    const escaped = diff.replace(/[&<>]/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[ch]));
    return /* html */ `
<!doctype html><html><body>
  <div style="display:flex; gap:8px; margin-bottom:10px;">
    <button id="apply">Apply</button>
    <button id="dismiss">Dismiss</button>
  </div>
  <pre style="white-space:pre; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace;">
${escaped}
  </pre>
  <script>
    const vscode = acquireVsCodeApi();
    document.getElementById('apply').onclick = () => vscode.postMessage({type:'apply'});
    document.getElementById('dismiss').onclick = () => vscode.postMessage({type:'dismiss'});
  </script>
</body></html>`;
}
//# sourceMappingURL=diffWebview.js.map