import * as path from 'path';

export type Hunk = {
  old_start: number;
  old_len: number;  
  new_start: number;
  new_len: number;  
  lines: string[];
};

export type FilePatch = {
  path: string;
  hunks: Hunk[];
};

export type PatchResponse = {
  project_root?: string;
  patches?: FilePatch[];
  unified_diff?: string;
};

/**
 * Build a unified diff text from structured patches.
 * This is used purely for preview in the webview; applying is done from the structured hunks.
 */
export function buildUnifiedDiff(projectRoot: string | undefined, patches: FilePatch[]): string {
  const out: string[] = [];

  for (const fp of patches) {
    const abs = fp.path.replace(/\\/g, '/');
    const aPath = abs.startsWith('/') ? `a${abs}` : `a/${abs}`;
    const bPath = abs.startsWith('/') ? `b${abs}` : `b/${abs}`;

    out.push(`diff --git ${aPath} ${bPath}`);
    out.push(`--- ${aPath}`);
    out.push(`+++ ${bPath}`);

    for (const h of fp.hunks) {
      const oldStart = h.old_start;
      const oldLen = h.old_len;
      const newStart = h.new_start;
      const newLen = h.new_len;

      out.push(`@@ -${oldStart},${oldLen} +${newStart},${newLen} @@`);

      for (const raw of h.lines) {
        const ln = raw.trim() === '```' ? '' : raw;
        console.log(`'${ln}'`);
        if (ln.startsWith('+') || ln.startsWith('-') || ln.startsWith(' ')) {
          out.push(ln);
        } else {
          out.push(' ' + ln);
        }
      }
    }

    out.push('');
  }

  let text = out.join('\n');
  if (!text.endsWith('\n')) text += '\n';
  return text;
}
