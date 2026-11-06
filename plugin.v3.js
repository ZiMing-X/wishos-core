// wishos-core / plugin.v3.js — read-only health plugin for the WishOS Core bundle.
//
// It does NOT assemble the preset (that is a pure-data row in cordis.patch.yml) and
// does not register skills (the preset's skill-filesystem root does). Its only job is
// a read-only, model-callable self-check so an installation can be verified without
// guessing from logs or a GUI round-trip:
//   1. the declared preset id is present in the agent-presets roster and is not `broken`
//   2. the `!!js` package-internal skills dir probe (evaluated by the Loader from the
//      row config) resolves to an existing dir containing the expected 8 skill dirs
//   3. every packaged SKILL.md file exists
//
// No writes, no config changes, no Host restart.

import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

export const name = 'wishos-core';
export const inject = ['agentPresets', 'tools'];

const HERE = dirname(fileURLToPath(import.meta.url));
const MANIFEST = join(HERE, 'skills.manifest.json');

function readManifest() {
  return JSON.parse(readFileSync(MANIFEST, 'utf8'));
}

export function apply(ctx, config) {
  const cfg = config && typeof config === 'object' ? config : {};
  const presetId = typeof cfg.presetId === 'string' && cfg.presetId ? cfg.presetId : 'wishos';
  const manifest = readManifest();
  const expected = manifest.skills ?? [];

  const health = async () => {
    const result = {
      ok: false,
      plugin: 'wishos-core',
      presetId,
      skillsDirProbe: typeof cfg.skillsDirProbe === 'string' ? cfg.skillsDirProbe : null,
      skillsDir: { resolved: null, exists: false, dirs: [] },
      files: [],
      preset: { found: false, broken: null, roster: [] },
      errors: [],
    };

    // 1) package files
    for (const entry of expected) {
      const file = join(HERE, 'skills', entry.dir, 'SKILL.md');
      result.files.push({ name: entry.name, dir: entry.dir, fileOk: existsSync(file) });
    }

    // 2) skills dir probe (evaluated by the Loader; we only read it)
    try {
      const p = cfg.skillsDirProbe;
      if (typeof p === 'string' && p) {
        result.skillsDir.resolved = p;
        result.skillsDir.exists = existsSync(p);
        if (result.skillsDir.exists) {
          result.skillsDir.dirs = readdirSync(p, { withFileTypes: true })
            .filter((d) => d.isDirectory())
            .map((d) => d.name)
            .sort();
        }
      } else {
        result.errors.push('skillsDirProbe 未由 Loader 求值（!!js 缺失或求值失败）');
      }
    } catch (error) {
      result.errors.push('skillsDirProbe 检查失败: ' + String(error));
    }

    // 3) preset roster + activation diagnostic
    try {
      const roster = await ctx.agentPresets.list();
      result.preset.roster = roster.map((r) => ({
        id: String(r.id),
        name: r.name === undefined ? null : String(r.name),
        order: typeof r.order === 'number' ? r.order : null,
        broken: r.broken === undefined ? null : String(r.broken),
      }));
      const hit = roster.find((r) => r.id === presetId);
      if (hit) {
        result.preset.found = true;
        result.preset.broken = hit.broken ?? null;
        if (hit.broken) result.errors.push('preset 激活诊断: ' + hit.broken);
      } else {
        result.errors.push('名册中找不到预设 ' + presetId);
      }
      const dup = roster.filter((r) => r.id === presetId).length;
      if (dup > 1) result.errors.push('同名预设 id 出现 ' + dup + ' 次（同 id 冲突）');
    } catch (error) {
      result.errors.push('agentPresets.list() 失败: ' + String(error));
    }

    const filesOk = result.files.every((f) => f.fileOk);
    const dirsOk = result.skillsDir.exists
      && expected.every((e) => result.skillsDir.dirs.includes(e.dir));
    result.ok = result.preset.found && !result.preset.broken && filesOk && dirsOk && result.errors.length === 0;
    // 宿主按 lossless JSON 校验工具返回值：统一经一次 JSON round-trip 去掉 undefined/非 plain 值。
    return JSON.parse(JSON.stringify(result));
  };

  ctx.tools.register({
    name: 'wishos_core_health',
    description: 'wishos-core 自检（只读）：核对包内 8 个 w-* 文件、!!js 解析出的预设技能根、以及 agent-presets 名册里的预设注册/激活诊断。不修改任何配置。',
    parameters: { type: 'object', properties: {} },
    output: {
      schema: { type: 'object', additionalProperties: true },
      render(_args, value) {
        const r = value ?? {};
        const lines = [`wishos-core 自检 ${r.ok ? '✅ 通过' : '🔴 未通过'} · preset=${r.presetId}`];
        lines.push('- 预设名册：' + (r.preset.found ? '找到 ✅' : '未找到 ❌') + (r.preset.broken ? ' · 激活异常：' + r.preset.broken : ' · 无 broken ✅'));
        lines.push('- 技能根（!!js 解析）：' + (r.skillsDir.exists ? r.skillsDir.resolved + ' ✅' : String(r.skillsDir.resolved) + ' ❌'));
        lines.push('- 包内技能目录：' + (r.skillsDir.dirs ?? []).length + ' 个 / 期望 ' + (r.files ?? []).length);
        for (const f of r.files ?? []) lines.push('  - ' + f.name + '：' + (f.fileOk ? '文件✅' : '文件❌'));
        for (const e of r.errors ?? []) lines.push('- ❌ ' + e);
        return [{ type: 'text', text: lines.join('\n') }];
      },
    },
    execute: health,
  });
}
