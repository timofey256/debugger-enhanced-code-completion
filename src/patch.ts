import * as vscode from 'vscode';
import * as fs from 'fs/promises';
import * as path from 'path';
import { FilePatch, PatchResponse } from './patchFormat';

/**
 * Apply patches provided by the server (structured hunks).
 * - Uses 1-based line numbers from hunks.
 * - Verifies context lines and old segment length.
 * - Applies multiple hunks per file with running offset.
 */
export async function applyPatchesFromResponse(resp: PatchResponse): Promise<boolean> {
  const ws = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  if (!ws) return false;
  const patches = resp.patches ?? [];
  if (!patches.length) {
    vscode.window.showWarningMessage('No structured patches to apply.');
    return false;
  }
  try {
    for (const fp of patches) {
      const ok = await applyFilePatch(ws, fp, resp.project_root);
      if (!ok) return false;
    }
    return true;
  } catch (e: any) {
    vscode.window.showErrorMessage(`Patch apply failed: ${e?.message ?? e}`);
    return false;
  }
}

async function applyFilePatch(workspaceRoot: string, fp: FilePatch, projectRoot?: string): Promise<boolean> {
  const targetAbs = (() => {
    if (projectRoot) {
      const rel = path.relative(projectRoot, fp.path);
      return path.join(workspaceRoot, rel);
    }
    return path.isAbsolute(fp.path) ? fp.path : path.join(workspaceRoot, fp.path);
  })();

  let text: string;
  try {
    text = await fs.readFile(targetAbs, 'utf8');
  } catch (e) {
    throw new Error(`Cannot read file to patch: ${targetAbs}`);
  }

  const eol = /\r\n/.test(text) ? '\r\n' : '\n';
  const { lines, hadTrailingNewline } = splitLogicalLines(text);

  let offset = 0;
  for (const [idx, h] of fp.hunks.entries()) {
    const sanitizedLines = h.lines.filter((ln) => {
      const t = ln.trim();
      const fence = t.startsWith('```'); // matches ``` and ```lang
      return !fence;
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
      } else if (kind === 'del') {
        expectedOld.push(asLine);
      } else { // add
        newSeg.push(asLine);
      }
    }

    if (expectedOld.length !== oldLen) {
      throw new Error(
        `Hunk length mismatch in ${targetAbs} at old_start=${h.old_start}. Expected old_len=${oldLen}, derived=${expectedOld.length}`
      );
    }
    if (newSeg.length !== newLen) {
      throw new Error(
        `Hunk length mismatch in ${targetAbs} at new_start=${h.new_start}. Expected new_len=${newLen}, derived=${newSeg.length}`
      );
    }

    lines.splice(startIndex, oldLen, ...newSeg);
    offset += (newLen - oldLen);
  }

  let finalText = lines.join(eol);
  if (hadTrailingNewline) finalText += eol;
  await fs.writeFile(targetAbs, finalText, 'utf8');
  return true;
}

function splitLogicalLines(text: string): { lines: string[]; hadTrailingNewline: boolean } {
  const eol = /\r\n/.test(text) ? '\r\n' : '\n';
  const parts = text.split(eol);
  const hadTrailingNewline = text.endsWith(eol);
  if (hadTrailingNewline) {
    parts.pop();
  }
  return { lines: parts, hadTrailingNewline };
}

function stripMarker(s: string): string {
  if (s.startsWith('+') || s.startsWith('-')) return s.slice(1);
  return s;
}
