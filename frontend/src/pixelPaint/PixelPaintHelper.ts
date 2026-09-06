/**
 * 巡展像素画：原图 → 24×24 × 官方 40 色。
 * 移植自 MAA 客户端 MaaWpfGui/Helper/PixelPaintHelper.cs（v6.17），算法逐段对齐：
 *   线性光面积采样 → CSS 风格滤镜 → 量化（None / FS 蛇形 0.6 / Atkinson / 插画优先）→ 按色分桶。
 * 最近色比对全部在 OKLab 感知空间（色板预转换缓存）。
 */

/** 网格边长（游戏像素编辑器为 24×24）。 */
export const GRID_SIZE = 24
/** 官方色板颜色数。 */
export const COLOR_COUNT = 40
/** 纯白在 40 色板中的下标（0-based）。 */
export const WHITE_COLOR_INDEX = 3
/** 预览图边长（像素）。 */
export const PREVIEW_PIXEL_SIZE = 216

/** 官方 40 色 RGB（与游戏色板顺序一致）。 */
export const PALETTE: ReadonlyArray<readonly [number, number, number]> = [
  [34, 34, 34], [180, 180, 180], [234, 231, 223], [255, 255, 255],
  [211, 47, 54], [156, 10, 0], [214, 12, 74], [230, 150, 141],
  [254, 152, 117], [247, 208, 192], [252, 239, 234], [251, 246, 232],
  [220, 210, 200], [226, 206, 171], [213, 99, 34], [212, 140, 66],
  [242, 153, 0], [249, 201, 51], [252, 228, 153], [179, 180, 122],
  [194, 218, 114], [108, 110, 0], [177, 145, 85], [169, 143, 116],
  [170, 146, 40], [63, 43, 18], [116, 73, 31], [83, 70, 88],
  [42, 36, 70], [57, 69, 153], [90, 69, 157], [186, 163, 215],
  [182, 188, 223], [169, 172, 190], [99, 171, 185], [180, 210, 220],
  [145, 216, 230], [71, 174, 160], [182, 211, 200], [39, 56, 100],
]

/** 原图到 24×24 网格的构图方式。 */
export type FitMode = 'crop' | 'contain' | 'stretch'
/** 量化抖动方式。 */
export type DitherMode = 'none' | 'floyd_steinberg' | 'atkinson' | 'illustration'

export interface ConvertOptions {
  fit: FitMode
  dither: DitherMode
  /** 对比度百分比，100 为原图。 */
  contrast: number
  /** 亮度百分比，100 为原图。 */
  brightness: number
  /** 饱和度百分比，0~200。 */
  saturation: number
  /** 是否跳过纯白格（不画）。 */
  skipWhite: boolean
}

export interface ColorGroup {
  /** 色板下标 0~39。 */
  color: number
  /** 格子坐标 [x, y]（左上为原点，x 右 y 下）。 */
  points: Array<[number, number]>
}

/** 像素画面板产出（引擎 params.pixel_paint 结构 + 统计）。 */
export interface PixelPaintResult {
  swipe: boolean
  grid_delay: number
  groups: ColorGroup[]
  painted: number
  group_count: number
}

export interface ConvertResult {
  /** 24×24 色号矩阵（行优先，值域 0~39）。 */
  matrix: number[][]
  /** 按色分组点列（已按 skipWhite 过滤）。 */
  groups: ColorGroup[]
  /** 需绘制格子总数。 */
  painted: number
}

// ── 色彩空间 ────────────────────────────────────────────────

/** sRGB 0~255 → 线性光 0~1（IEC 61966-2-1 解伽马）。 */
function srgb8ToLinear(v8: number): number {
  const x = v8 / 255
  return x >= 0.04045 ? Math.pow((x + 0.055) / 1.055, 2.4) : x / 12.92
}

/** 线性光 0~1 → sRGB 0~255（反向伽马编码）。 */
function linearToSrgb8(lin: number): number {
  const v = lin <= 0.0031308 ? lin * 12.92 : 1.055 * Math.pow(lin, 1 / 2.4) - 0.055
  return v * 255
}

export interface Oklab {
  L: number
  A: number
  B: number
}

/** sRGB 8 位 → OKLab（Björn 2020 标准矩阵）。 */
export function srgb8ToOklab(r8: number, g8: number, b8: number): Oklab {
  const r = srgb8ToLinear(r8)
  const g = srgb8ToLinear(g8)
  const b = srgb8ToLinear(b8)
  const l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
  const m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
  const s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
  const l_ = Math.cbrt(l)
  const m_ = Math.cbrt(m)
  const s_ = Math.cbrt(s)
  return {
    L: 0.2104542553 * l_ + 0.793617785 * m_ - 0.0040720468 * s_,
    A: 1.9779984951 * l_ - 2.428592205 * m_ + 0.4505937099 * s_,
    B: 0.0259040371 * l_ + 0.7827717662 * m_ - 0.808675766 * s_,
  }
}

function oklabSqDist(p: Oklab, q: Oklab): number {
  const dL = p.L - q.L
  const dA = p.A - q.A
  const dB = p.B - q.B
  return dL * dL + dA * dA + dB * dB
}

/** 色板 OKLab 预转换缓存（热路径避免反复转换）。 */
const PALETTE_OKLAB: Oklab[] = PALETTE.map((c) => srgb8ToOklab(c[0], c[1], c[2]))

/** 给定 OKLab 坐标，在 40 色板中找最近项。 */
function nearestPaletteIndex(c: Oklab): number {
  let best = 0
  let bestD = Infinity
  for (let i = 0; i < PALETTE_OKLAB.length; i++) {
    const d = oklabSqDist(c, PALETTE_OKLAB[i])
    if (d < bestD) {
      bestD = d
      best = i
    }
  }
  return best
}

// ── 图像预处理 ──────────────────────────────────────────────

/** 解码后的 BGRA 像素图。 */
export interface BgraImage {
  width: number
  height: number
  /** BGRA 顺序像素数据，stride = width*4。 */
  pixels: Uint8ClampedArray
}

/** 任意位图源 → BGRA32 像素图（Canvas 离屏转换）。 */
export function loadBgra(source: CanvasImageSource, w: number, h: number): BgraImage {
  const cv = document.createElement('canvas')
  cv.width = w
  cv.height = h
  const ctx = cv.getContext('2d', { willReadFrequently: true })
  if (!ctx) throw new Error('Canvas 2D 上下文不可用')
  ctx.drawImage(source, 0, 0)
  const data = ctx.getImageData(0, 0, w, h)
  return { width: w, height: h, pixels: data.data }
}

/**
 * 解码并（可选）去边。恰好 24×24 视为外部已处理好的像素画，不去边。
 * 内部等价于客户端 Prepare()。
 */
export function prepare(source: CanvasImageSource, w: number, h: number, trimEmptyBorder = true): BgraImage {
  let bgra = loadBgra(source, w, h)
  if (trimEmptyBorder && !(bgra.width === GRID_SIZE && bgra.height === GRID_SIZE)) {
    bgra = trimBorder(bgra) ?? bgra
  }
  return bgra
}

/** 裁掉四周透明（alpha<16）与近白（RGB≥250）像素，返回内容包围盒；整图空白返回 null。 */
function trimBorder(src: BgraImage): BgraImage | null {
  const { width: w, height: h, pixels: px } = src
  const isContent = (i: number): boolean => {
    if (px[i + 3] < 16) return false
    return px[i + 2] < 250 || px[i + 1] < 250 || px[i] < 250 // BGRA → r/g/b
  }
  let minX = w, minY = h, maxX = -1, maxY = -1
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      if (isContent((y * w + x) * 4)) {
        if (x < minX) minX = x
        if (y < minY) minY = y
        if (x > maxX) maxX = x
        if (y > maxY) maxY = y
      }
    }
  }
  if (maxX < minX || maxY < minY) return null
  const nw = maxX - minX + 1
  const nh = maxY - minY + 1
  if (nw === w && nh === h) return src
  const np = new Uint8ClampedArray(nw * nh * 4)
  for (let y = 0; y < nh; y++) {
    np.set(px.subarray(((minY + y) * w + minX) * 4, ((minY + y) * w + minX) * 4 + nw * 4), y * nw * 4)
  }
  return { width: nw, height: nh, pixels: np }
}

/** 读取某像素的 sRGB 颜色，透明像素与白底合成。 */
function getRgb(src: BgraImage, x: number, y: number): [number, number, number] {
  const i = (y * src.width + x) * 4
  const a = src.pixels[i + 3] / 255
  const b = src.pixels[i]
  const g = src.pixels[i + 1]
  const r = src.pixels[i + 2]
  return [r * a + 255 * (1 - a), g * a + 255 * (1 - a), b * a + 255 * (1 - a)]
}

/** 源图上双线性插值采样；取景区外返回白色。 */
function sampleBilinear(src: BgraImage, sx: number, sy: number): [number, number, number] {
  if (sx < 0 || sy < 0 || sx >= src.width || sy >= src.height) return [255, 255, 255]
  const x0 = Math.floor(sx)
  const y0 = Math.floor(sy)
  const x1 = Math.min(x0 + 1, src.width - 1)
  const y1 = Math.min(y0 + 1, src.height - 1)
  const tx = sx - x0
  const ty = sy - y0
  const c00 = getRgb(src, x0, y0)
  const c10 = getRgb(src, x1, y0)
  const c01 = getRgb(src, x0, y1)
  const c11 = getRgb(src, x1, y1)
  const lerp = (a: number, b: number, t: number) => a + (b - a) * t
  return [
    lerp(lerp(c00[0], c10[0], tx), lerp(c01[0], c11[0], tx), ty),
    lerp(lerp(c00[1], c10[1], tx), lerp(c01[1], c11[1], tx), ty),
    lerp(lerp(c00[2], c10[2], tx), lerp(c01[2], c11[2], tx), ty),
  ]
}

/** 一格采样结果：线性光均值（编码回 sRGB）+ 格内子样（供插画优先 medoid 选取）。 */
interface CellSample {
  r: number
  g: number
  b: number
  /** 子样扁平数组 [r,g,b, ...]，sRGB 0~255。 */
  subs: number[]
}

/** 内容图按 Fit 采样到 24×24 格（线性光空间面积平均；源图恰 24×24 时逐像素直取）。 */
function sampleToGrid(src: BgraImage, options: ConvertOptions): CellSample[][] {
  if (src.width === GRID_SIZE && src.height === GRID_SIZE) {
    const exact: CellSample[][] = []
    for (let y = 0; y < GRID_SIZE; y++) {
      const row: CellSample[] = []
      for (let x = 0; x < GRID_SIZE; x++) {
        const [r, g, b] = getRgb(src, x, y)
        row.push({ r, g, b, subs: [r, g, b] })
      }
      exact.push(row)
    }
    return exact
  }

  const srcW = src.width
  const srcH = src.height
  let mapX0: number, mapY0: number, mapW: number, mapH: number
  switch (options.fit) {
    case 'stretch':
      mapX0 = 0; mapY0 = 0; mapW = srcW; mapH = srcH
      break
    case 'contain': {
      const scale = Math.max(srcW / GRID_SIZE, srcH / GRID_SIZE)
      mapW = GRID_SIZE * scale
      mapH = GRID_SIZE * scale
      mapX0 = (srcW - mapW) / 2
      mapY0 = (srcH - mapH) / 2
      break
    }
    default: {
      // crop = cover：源图内最大 1:1 采样矩形
      const scale = Math.min(srcW / GRID_SIZE, srcH / GRID_SIZE)
      mapW = GRID_SIZE * scale
      mapH = GRID_SIZE * scale
      mapX0 = (srcW - mapW) / 2
      mapY0 = (srcH - mapH) / 2
      break
    }
  }

  // 格内子样数：按源图覆盖面积自适应，最多 4×4
  const cellW = mapW / GRID_SIZE
  const cellH = mapH / GRID_SIZE
  const sxN = Math.min(4, Math.max(1, Math.ceil(cellW)))
  const syN = Math.min(4, Math.max(1, Math.ceil(cellH)))

  const grid: CellSample[][] = []
  for (let gy = 0; gy < GRID_SIZE; gy++) {
    const row: CellSample[] = []
    for (let gx = 0; gx < GRID_SIZE; gx++) {
      const gx0 = mapX0 + (gx / GRID_SIZE) * mapW
      const gy0 = mapY0 + (gy / GRID_SIZE) * mapH
      const gw = mapW / GRID_SIZE
      const gh = mapH / GRID_SIZE
      const n = sxN * syN
      const subs: number[] = new Array(n * 3)
      let sumLR = 0, sumLG = 0, sumLB = 0
      let k = 0
      for (let iy = 0; iy < syN; iy++) {
        for (let ix = 0; ix < sxN; ix++) {
          const sx = gx0 + ((ix + 0.5) / sxN) * gw
          const sy = gy0 + ((iy + 0.5) / syN) * gh
          const [cr, cg, cb] = sampleBilinear(src, sx, sy)
          subs[k++] = cr
          subs[k++] = cg
          subs[k++] = cb
          sumLR += srgb8ToLinear(cr)
          sumLG += srgb8ToLinear(cg)
          sumLB += srgb8ToLinear(cb)
        }
      }
      // 线性光平均后编码回 sRGB（避免 sRGB 直接平均交界偏暗）
      row.push({
        r: linearToSrgb8(sumLR / n),
        g: linearToSrgb8(sumLG / n),
        b: linearToSrgb8(sumLB / n),
        subs,
      })
    }
    grid.push(row)
  }
  return grid
}

/** CSS 风格滤镜（固定顺序：亮度 → 对比度 → 饱和度），原地修改。 */
function applyCssLikeFilters(grid: CellSample[][], contrast: number, brightness: number, saturation: number): void {
  if (Math.abs(contrast - 1) < 1e-6 && Math.abs(brightness - 1) < 1e-6 && Math.abs(saturation - 1) < 1e-6) return
  const clamp = (v: number) => Math.min(255, Math.max(0, v))
  const filter = (r: number, g: number, b: number): [number, number, number] => {
    r *= brightness
    g *= brightness
    b *= brightness
    r = ((r / 255 - 0.5) * contrast + 0.5) * 255
    g = ((g / 255 - 0.5) * contrast + 0.5) * 255
    b = ((b / 255 - 0.5) * contrast + 0.5) * 255
    const luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
    r = luma + (r - luma) * saturation
    g = luma + (g - luma) * saturation
    b = luma + (b - luma) * saturation
    return [clamp(r), clamp(g), clamp(b)]
  }
  for (let y = 0; y < GRID_SIZE; y++) {
    for (let x = 0; x < GRID_SIZE; x++) {
      const cell = grid[y][x]
      const [ar, ag, ab] = filter(cell.r, cell.g, cell.b)
      const subs = cell.subs
      for (let i = 0; i < subs.length; i += 3) {
        const [fr, fg, fb] = filter(subs[i], subs[i + 1], subs[i + 2])
        subs[i] = fr
        subs[i + 1] = fg
        subs[i + 2] = fb
      }
      grid[y][x] = { r: ar, g: ag, b: ab, subs }
    }
  }
}

/** 最近邻量化（None / FS 蛇形部分误差扩散 / Atkinson 对称扩散）。 */
function quantize(sample: CellSample[][], dither: DitherMode): number[][] {
  const work: [number, number, number][][] = sample.map((row) => row.map((c) => [c.r, c.g, c.b]))
  const result: number[][] = []

  const addError = (x: number, y: number, er: number, eg: number, eb: number, factor: number) => {
    if (x < 0 || y < 0 || x >= GRID_SIZE || y >= GRID_SIZE) return
    const p = work[y][x]
    work[y][x] = [
      Math.min(255, Math.max(0, p[0] + er * factor)),
      Math.min(255, Math.max(0, p[1] + eg * factor)),
      Math.min(255, Math.max(0, p[2] + eb * factor)),
    ]
  }

  for (let y = 0; y < GRID_SIZE; y++) {
    result.push(new Array(GRID_SIZE))
    // 蛇形扫描：奇数行反向，消除误差长期偏向一侧的条纹（仅 FS）
    const serpentine = dither === 'floyd_steinberg' && y % 2 === 1
    const fwd = serpentine ? -1 : 1
    for (let i = 0; i < GRID_SIZE; i++) {
      const x = serpentine ? GRID_SIZE - 1 - i : i
      const old = work[y][x]
      const or = Math.min(255, Math.max(0, Math.round(old[0])))
      const og = Math.min(255, Math.max(0, Math.round(old[1])))
      const ob = Math.min(255, Math.max(0, Math.round(old[2])))
      const idx = nearestPaletteIndex(srgb8ToOklab(or, og, ob))
      result[y][x] = idx
      if (dither === 'none') continue
      const [nr, ng, nb] = PALETTE[idx]
      const er = old[0] - nr
      const eg = old[1] - ng
      const eb = old[2] - nb
      if (dither === 'floyd_steinberg') {
        // 24×24 全强度扩散噪点过密，仅扩散部分误差（系数 0.6，对齐客户端）
        const fsStrength = 0.6
        addError(x + fwd, y, er, eg, eb, (7 / 16) * fsStrength)
        addError(x - fwd, y + 1, er, eg, eb, (3 / 16) * fsStrength)
        addError(x, y + 1, er, eg, eb, (5 / 16) * fsStrength)
        addError(x + fwd, y + 1, er, eg, eb, (1 / 16) * fsStrength)
      } else {
        // Atkinson：对称扩散 6/8 误差
        const f = 1 / 8
        addError(x + 1, y, er, eg, eb, f)
        addError(x + 2, y, er, eg, eb, f)
        addError(x - 1, y + 1, er, eg, eb, f)
        addError(x, y + 1, er, eg, eb, f)
        addError(x + 1, y + 1, er, eg, eb, f)
        addError(x, y + 2, er, eg, eb, f)
      }
    }
  }
  return result
}

/** 插画优先量化：medoid 代表色 + 边缘感知 ICM 迭代 MRF 平滑（对齐客户端默认档）。 */
function quantizeIllustration(sample: CellSample[][]): number[][] {
  // 1. 每格代表色：最接近格内 OKLab 均值的真实子样
  const repr: Oklab[][] = []
  for (let y = 0; y < GRID_SIZE; y++) {
    const row: Oklab[] = []
    for (let x = 0; x < GRID_SIZE; x++) {
      const subs = sample[y][x].subs
      const n = subs.length / 3
      if (n === 0) {
        row.push(srgb8ToOklab(255, 255, 255))
        continue
      }
      const lab: Oklab[] = new Array(n)
      let sumL = 0, sumA = 0, sumB = 0
      for (let i = 0; i < n; i++) {
        const v = srgb8ToOklab(
          Math.min(255, Math.max(0, Math.round(subs[i * 3]))),
          Math.min(255, Math.max(0, Math.round(subs[i * 3 + 1]))),
          Math.min(255, Math.max(0, Math.round(subs[i * 3 + 2]))),
        )
        lab[i] = v
        sumL += v.L
        sumA += v.A
        sumB += v.B
      }
      const mL = sumL / n, mA = sumA / n, mB = sumB / n
      let best = 0
      let bestD = Infinity
      for (let i = 0; i < n; i++) {
        const d = (lab[i].L - mL) ** 2 + (lab[i].A - mA) ** 2 + (lab[i].B - mB) ** 2
        if (d < bestD) {
          bestD = d
          best = i
        }
      }
      row.push(lab[best])
    }
    repr.push(row)
  }

  // 2. 数据项：每格每色板的 OKLab 平方距离
  const dataCost: number[][][] = []
  for (let y = 0; y < GRID_SIZE; y++) {
    const rowY: number[][] = []
    for (let x = 0; x < GRID_SIZE; x++) {
      const rowC: number[] = new Array(COLOR_COUNT)
      const m = repr[y][x]
      for (let c = 0; c < COLOR_COUNT; c++) {
        rowC[c] = oklabSqDist(m, PALETTE_OKLAB[c])
      }
      rowY.push(rowC)
    }
    dataCost.push(rowY)
  }

  // 3. 初始标号：数据项最小色板
  const labels: number[][] = []
  for (let y = 0; y < GRID_SIZE; y++) {
    const row: number[] = new Array(GRID_SIZE)
    for (let x = 0; x < GRID_SIZE; x++) {
      let bestC = 0
      let bestE = Infinity
      for (let c = 0; c < COLOR_COUNT; c++) {
        if (dataCost[y][x][c] < bestE) {
          bestE = dataCost[y][x][c]
          bestC = c
        }
      }
      row[x] = bestC
    }
    labels.push(row)
  }

  // 4. ICM 迭代：每格选「数据项 + 平滑项」最小的标号
  //    平滑项 = 指数衰减软约束（邻格原图色越近惩罚越高，越倾向同色）
  const strength = 0.0012
  const sigma2 = 0.0025
  for (let iter = 0; iter < 3; iter++) {
    let changed = false
    for (let y = 0; y < GRID_SIZE; y++) {
      for (let x = 0; x < GRID_SIZE; x++) {
        const m = repr[y][x]
        let bestLabel = labels[y][x]
        let bestEnergy = Infinity
        const wL = x > 0 ? strength * Math.exp(-oklabSqDist(m, repr[y][x - 1]) / sigma2) : 0
        const wR = x < GRID_SIZE - 1 ? strength * Math.exp(-oklabSqDist(m, repr[y][x + 1]) / sigma2) : 0
        const wU = y > 0 ? strength * Math.exp(-oklabSqDist(m, repr[y - 1][x]) / sigma2) : 0
        const wD = y < GRID_SIZE - 1 ? strength * Math.exp(-oklabSqDist(m, repr[y + 1][x]) / sigma2) : 0
        for (let c = 0; c < COLOR_COUNT; c++) {
          let energy = dataCost[y][x][c]
          if (x > 0 && labels[y][x - 1] !== c) energy += wL
          if (x < GRID_SIZE - 1 && labels[y][x + 1] !== c) energy += wR
          if (y > 0 && labels[y - 1][x] !== c) energy += wU
          if (y < GRID_SIZE - 1 && labels[y + 1][x] !== c) energy += wD
          if (energy < bestEnergy) {
            bestEnergy = energy
            bestLabel = c
          }
        }
        if (bestLabel !== labels[y][x]) {
          labels[y][x] = bestLabel
          changed = true
        }
      }
    }
    if (!changed) break
  }
  return labels
}

/** 把色号矩阵按色板下标分桶（skipWhite 时跳过纯白格）。 */
export function buildGroups(matrix: number[][], skipWhite: boolean): ColorGroup[] {
  const buckets: Array<Array<[number, number]>> = Array.from({ length: COLOR_COUNT }, () => [])
  for (let y = 0; y < GRID_SIZE; y++) {
    for (let x = 0; x < GRID_SIZE; x++) {
      const idx = matrix[y][x]
      if (skipWhite && idx === WHITE_COLOR_INDEX) continue
      buckets[idx].push([x, y])
    }
  }
  const groups: ColorGroup[] = []
  for (let c = 0; c < COLOR_COUNT; c++) {
    if (buckets[c].length) groups.push({ color: c, points: buckets[c] })
  }
  return groups
}

/** 把色号矩阵渲染成等比放大的预览 ImageData（每格 cellPx 像素色块）。 */
export function renderPreviewData(matrix: number[][], cellPx = PREVIEW_PIXEL_SIZE / GRID_SIZE): ImageData {
  const size = GRID_SIZE * cellPx
  const out = new ImageData(size, size)
  for (let y = 0; y < GRID_SIZE; y++) {
    for (let x = 0; x < GRID_SIZE; x++) {
      const [r, g, b] = PALETTE[matrix[y][x]]
      for (let dy = 0; dy < cellPx; dy++) {
        for (let dx = 0; dx < cellPx; dx++) {
          const i = (((y * cellPx + dy) * size) + x * cellPx + dx) * 4
          out.data[i] = r
          out.data[i + 1] = g
          out.data[i + 2] = b
          out.data[i + 3] = 255
        }
      }
    }
  }
  return out
}

/**
 * 完整转换流水线：已 prepare 的图 → 色号矩阵 + 分组点列。
 * 等价客户端 Convert(PreparedImage, options, skipWhite)。
 */
export function convert(prepared: BgraImage, options: ConvertOptions): ConvertResult {
  const grid = sampleToGrid(prepared, options)
  applyCssLikeFilters(grid, options.contrast / 100, options.brightness / 100, options.saturation / 100)
  const matrix = options.dither === 'illustration' ? quantizeIllustration(grid) : quantize(grid, options.dither)
  const groups = buildGroups(matrix, options.skipWhite)
  const painted = groups.reduce((s, g) => s + g.points.length, 0)
  return { matrix, groups, painted }
}
