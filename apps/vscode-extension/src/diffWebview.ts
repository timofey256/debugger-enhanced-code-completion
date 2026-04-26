import * as vscode from 'vscode';

export async function showDiffWebview(
  ctx: vscode.ExtensionContext,
  diff: string,
  onApply: () => Promise<boolean>
) {
  const panel = vscode.window.createWebviewPanel(
    'pytestSmartDebugger.diff',
    'Suggested Fix (unified diff)',
    vscode.ViewColumn.Active,
    { enableScripts: true, retainContextWhenHidden: false }
  );

  panel.webview.html = render(diff);
  panel.webview.onDidReceiveMessage(async (msg) => {
    if (msg.type === 'apply') {
      const ok = await onApply();
      if (ok) panel.dispose();
    } else if (msg.type === 'dismiss') {
      panel.dispose();
    }
  });
}

function render(diff: string) {
  const escaped = diff.replace(/[&<>]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[ch]!));
  return /* html */`
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
