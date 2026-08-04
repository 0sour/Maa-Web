'use strict';

const path = require('path');
const fsp = require('fs/promises');

/* 各主题分队表（参考 MAA 客户端 RoguelikeSettingsUserControlModel） */
const SQUADS = {
  Phantom: [
    ['GatheringSquad', '集群分队'],
    ['SpearheadSquad', '矛头分队'],
    ['ResearchSquad', '研究分队'],
  ],
  Mizuki: [
    ['GatheringSquad', '集群分队'],
    ['SpearheadSquad', '矛头分队'],
    ['IS2NewSquad1', '心胜于物分队'],
    ['IS2NewSquad2', '物尽其用分队'],
    ['IS2NewSquad3', '以人为本分队'],
    ['ResearchSquad', '研究分队'],
  ],
  Sami: [
    ['GatheringSquad', '集群分队'],
    ['SpearheadSquad', '矛头分队'],
    ['IS3NewSquad1', '永恒狩猎分队'],
    ['IS3NewSquad2', '生活至上分队'],
    ['IS3NewSquad3', '科学主义分队'],
    ['IS3NewSquad4', '特训分队'],
  ],
  Sarkaz: [
    ['GatheringSquad', '集群分队'],
    ['SpearheadSquad', '矛头分队'],
    ['IS4NewSquad1', '魂灵护送分队'],
    ['IS4NewSquad2', '博闻广记分队'],
    ['IS4NewSquad3', '蓝图测绘分队'],
    ['IS4NewSquad4', '因地制宜分队'],
    ['IS4NewSquad5', '异想天开分队'],
    ['IS4NewSquad6', '点刺成锭分队'],
    ['IS4NewSquad7', '拟态学者分队'],
    ['IS4NewSquad8', '专业人士分队'],
  ],
  JieGarden: [
    ['SpecialForceSquad', '特勤分队'],
    ['IS5NewSquad1', '高台突破分队'],
    ['IS5NewSquad2', '地面突破分队'],
    ['IS5NewSquad3', '游客分队'],
    ['IS5NewSquad4', '司岁台分队'],
    ['IS5NewSquad5', '天师府分队'],
    ['IS5NewSquad6', '花团锦簇分队'],
    ['IS5NewSquad7', '棋行险着分队'],
    ['IS5NewSquad8', '岁影回音分队'],
    ['IS5NewSquad9', '代理人分队'],
    ['IS5NewSquad10', '知学分队'],
    ['IS5NewSquad11', '商贾分队'],
  ],
};

const THEME_DIR = {
  Phantom: 'Phantom',
  Mizuki: 'Mizuki',
  Sami: 'Sami',
  Sarkaz: 'Sarkaz',
  JieGarden: 'JieGarden',
};

let dataDir = '';
let opCache = {}; // theme -> { mtime, groups, operators }

function init(dir) {
  dataDir = dir || '';
}

async function getOperators(theme) {
  const dir = THEME_DIR[theme];
  if (!dir) return { groups: [], operators: [] };
  const file = path.join(dataDir, 'resource', 'roguelike', dir, 'recruitment.json');
  try {
    const st = await fsp.stat(file);
    const cached = opCache[theme];
    if (cached && cached.mtime === st.mtimeMs) return cached;
    const j = JSON.parse(await fsp.readFile(file, 'utf8'));
    const groups = [];
    const seen = new Set();
    for (const item of Array.isArray(j.priority) ? j.priority : []) {
      if (!item || typeof item !== 'object') continue;
      const name = item.name;
      const members = [];
      for (const o of Array.isArray(item.opers) ? item.opers : []) {
        if (!o || typeof o !== 'object') continue;
        // 参考官方 UpdateRoguelikeCoreCharList：仅 is_start=true 的开局核心干员
        if (o.is_start !== true) continue;
        const oname = typeof o.name === 'string' ? o.name : '';
        if (oname) members.push(oname);
        if (oname && !seen.has(oname)) seen.add(oname);
      }
      if (name && members.length) groups.push({ name, members });
    }
    const result = { mtime: st.mtimeMs, groups, operators: [...seen] };
    opCache[theme] = result;
    return result;
  } catch {
    return { groups: [], operators: [] };
  }
}

async function list(theme) {
  const squads = (SQUADS[theme] || []).map(([value, label]) => ({ value, label }));
  const { groups, operators } = await getOperators(theme);
  return { theme, squads, groups, operators };
}

module.exports = { init, list };
