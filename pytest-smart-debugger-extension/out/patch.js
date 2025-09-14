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
exports.applyPatchesFromResponse = applyPatchesFromResponse;
const vscode = __importStar(require("vscode"));
const fs = __importStar(require("fs/promises"));
const path = __importStar(require("path"));
/**
 * Apply patches provided by the server (structured hunks).
 * - Uses 1-based line numbers from hunks.
 * - Verifies context lines and old segment length.
 * - Applies multiple hunks per file with running offset.
 */
async function applyPatchesFromResponse(resp) {
    const ws = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
    if (!ws)
        return false;
    const patches = resp.patches ?? [];
    if (!patches.length) {
        vscode.window.showWarningMessage('No structured patches to apply.');
        return false;
    }
    try {
        for (const fp of patches) {
            const ok = await applyFilePatch(ws, fp, resp.project_root);
            if (!ok)
                return false;
        }
        return true;
    }
    catch (e) {
        vscode.window.showErrorMessage(`Patch apply failed: ${e?.message ?? e}`);
        return false;
    }
}
async function applyFilePatch(workspaceRoot, fp, projectRoot) {
    const targetAbs = (() => {
        if (projectRoot) {
            const rel = path.relative(projectRoot, fp.path);
            return path.join(workspaceRoot, rel);
        }
        return path.isAbsolute(fp.path) ? fp.path : path.join(workspaceRoot, fp.path);
    })();
    let text;
    try {
        text = await fs.readFile(targetAbs, 'utf8');
    }
    catch (e) {
        throw new Error(`Cannot read file to patch: ${targetAbs}`);
    }
    const eol = /\r\n/.test(text) ? '\r\n' : '\n';
    const { lines, hadTrailingNewline } = splitLogicalLines(text);
    let offset = 0;
    for (const [idx, h] of fp.hunks.entries()) {
        let fenceCount = 0;
        const sanitizedLines = h.lines.filter((ln) => {
            const t = ln.trim();
            if (t.startsWith("```")) {
                fenceCount++;
                return false;
            }
            return fenceCount < 2;
        });
        const startIndex = Math.max(0, h.old_start - 1 + offset);
        const oldLen = h.old_len;
        const newLen = h.new_len;
        const expectedOld = [];
        const newSeg = [];
        for (const raw of sanitizedLines) {
            const l = raw.startsWith(' ') ? raw.slice(1) : raw;
            const kind = l.startsWith('+') ? 'add' : l.startsWith('-') ? 'del' : 'ctx';
            const body = stripMarker(l);
            const asLine = body === ' ' ? '' : body;
            if (kind === 'ctx') {
                expectedOld.push(asLine);
                newSeg.push(asLine);
            }
            else if (kind === 'del') {
                expectedOld.push(asLine);
            }
            else { // add
                newSeg.push(asLine);
            }
        }
        lines.splice(startIndex, oldLen, ...newSeg);
        offset += (newLen - oldLen);
    }
    let finalText = lines.join(eol);
    if (hadTrailingNewline)
        finalText += eol;
    await fs.writeFile(targetAbs, finalText, 'utf8');
    return true;
}
function splitLogicalLines(text) {
    const eol = /\r\n/.test(text) ? '\r\n' : '\n';
    const parts = text.split(eol);
    const hadTrailingNewline = text.endsWith(eol);
    if (hadTrailingNewline) {
        parts.pop();
    }
    return { lines: parts, hadTrailingNewline };
}
function stripMarker(s) {
    if (s.startsWith('+') || s.startsWith('-'))
        return s.slice(1);
    return s;
}
//# sourceMappingURL=patch.js.map