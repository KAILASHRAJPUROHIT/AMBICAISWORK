'use strict';

// Local-only preview analyser. Frames arrive as transferable ImageBitmaps;
// nothing leaves the phone and no network request is made by this worker.
const previousFrames = new Map();
let analysisCanvas = null;

const clamp = (value, low, high) => Math.max(low, Math.min(high, value));

function looksLikeGold(r, g, b) {
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const delta = max - min;
  const saturation = max ? delta / max : 0;
  const yLuma = 0.299 * r + 0.587 * g + 0.114 * b;
  const cb = 128 - 0.168736 * r - 0.331264 * g + 0.5 * b;
  const cr = 128 + 0.5 * r - 0.418688 * g - 0.081312 * b;
  return yLuma > 35 && yLuma < 245 &&
    delta > 55 &&
    saturation > 0.34 &&
    r > 100 && g > 60 && b > 18 &&
    r - b >= 45 &&
    r - g >= 10 &&
    g - b >= 5 &&
    r >= g &&
    g >= b * 0.6 &&
    cr >= 138 && cr <= 210 &&
    cb >= 72 && cb <= 145;
}

function looksLikeSilver(r, g, b) {
  // Silver/white-gold/platinum has the opposite colour signature to gold:
  // near-achromatic rather than warm-saturated. Bounded away from black
  // velvet (too dark), skin (real r-g-b delta from blood/melanin), and
  // near-white paper/clipped highlights (handled separately by
  // clippedRatio, so kept out of this band rather than double-counted).
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const delta = max - min;
  const saturation = max ? delta / max : 0;
  const yLuma = 0.299 * r + 0.587 * g + 0.114 * b;
  return yLuma > 70 && yLuma < 240 &&
    saturation < 0.14 &&
    delta < 30 &&
    max > 90;
}

function looksLikeMetal(r, g, b) {
  return looksLikeGold(r, g, b) || looksLikeSilver(r, g, b);
}

function findDarkSupportBounds(data, width, height, roi, tagMode) {
  const step = tagMode ? 5 : 4;
  const startX = Math.max(0, tagMode ? Math.round(width * 0.12) : Math.round(width * 0.08));
  const endX = Math.min(width, tagMode ? Math.round(width * 0.88) : Math.round(width * 0.92));
  const startY = Math.max(0, tagMode ? Math.round(height * 0.10) : Math.round(height * 0.08));
  const endY = Math.min(height, tagMode ? Math.round(height * 0.90) : Math.round(height * 0.92));
  const cols = Math.max(1, Math.ceil((endX - startX) / step));
  const rows = Math.max(1, Math.ceil((endY - startY) / step));
  const mask = new Uint8Array(cols * rows);
  let dark = 0;

  for (let row = 0; row < rows; row += 1) {
    for (let col = 0; col < cols; col += 1) {
      const x = Math.min(width - 1, startX + col * step);
      const y = Math.min(height - 1, startY + row * step);
      const index = (y * width + x) * 4;
      const r = data[index];
      const g = data[index + 1];
      const b = data[index + 2];
      const max = Math.max(r, g, b);
      const min = Math.min(r, g, b);
      const delta = max - min;
      const yLuma = 0.299 * r + 0.587 * g + 0.114 * b;
      const sat = max ? delta / max : 0;
      const darkPixel =
        yLuma < 105 &&
        max < 155 &&
        delta < 95 &&
        sat < 0.90;
      if (darkPixel) {
        mask[row * cols + col] = 1;
        dark += 1;
      }
    }
  }
  if (!dark) return null;

  const visited = new Uint8Array(mask.length);
  const stack = [];
  const centerX = 0.5;
  const centerY = 0.5;
  let best = null;
  let bestScore = -Infinity;

  function scoreRect(minCol, minRow, maxCol, maxRow, size) {
    const x0 = startX + minCol * step;
    const y0 = startY + minRow * step;
    const x1 = startX + (maxCol + 1) * step;
    const y1 = startY + (maxRow + 1) * step;
    const boxW = Math.max(1, x1 - x0);
    const boxH = Math.max(1, y1 - y0);
    const area = boxW * boxH;
    const fill = clamp((size * step * step) / area, 0, 1);
    const minDim = Math.min(boxW, boxH);
    const aspect = boxW / boxH;
    const areaRatio = area / (width * height);
    if (minDim < 35) return null;
    // Close tray captures legitimately contain one large black display card.
    // The old 8% ceiling rejected that card, then searched the entire frame
    // and merged unrelated gold ornaments and wooden reflections together.
    if (areaRatio < 0.0025 || areaRatio > 0.58) return null;
    if (boxW > (endX - startX) * 0.97 || boxH > (endY - startY) * 0.97) return null;
    if (aspect < 0.25 || aspect > 4.0) return null;
    if (fill < 0.18) return null;
    const sampleStep = Math.max(3, step);
    let gold = 0;
    let total = 0;
    for (let y = y0; y < y1; y += sampleStep) {
      for (let x = x0; x < x1; x += sampleStep) {
        const index = (Math.min(height - 1, y) * width + Math.min(width - 1, x)) * 4;
        const r = data[index];
        const g = data[index + 1];
        const b = data[index + 2];
        if (looksLikeMetal(r, g, b)) gold += 1;
        total += 1;
      }
    }
    const goldRatio = total ? gold / total : 0;
    const boxCx = (x0 + x1) / 2 / width;
    const boxCy = (y0 + y1) / 2 / height;
    const centerDistance = Math.abs(boxCx - centerX) + Math.abs(boxCy - centerY);
    const edgeDistance = Math.min(minCol, minRow, cols - 1 - maxCol, rows - 1 - maxRow);
    const shapeScore = 1 - clamp(Math.abs(Math.log(Math.max(aspect, 0.001))) / 1.25, 0, 1);
    const scaleScore = 1 - clamp(Math.abs(Math.log(Math.max(areaRatio, 0.0005) / 0.12)) / 2.4, 0, 1);
    const edgeScore = clamp(edgeDistance / 4, 0, 1);
    const score = goldRatio * 5.8 + fill * 2.4 + shapeScore * 1.3 + scaleScore * 1.6 + edgeScore * 1.4 - centerDistance * 2.0;
    return {
      score,
      x0: clamp((x0) / width, 0, 1),
      y0: clamp((y0) / height, 0, 1),
      x1: clamp((x1) / width, 0, 1),
      y1: clamp((y1) / height, 0, 1),
      goldRatio,
      fill,
      areaRatio,
    };
  }

  for (let start = 0; start < mask.length; start += 1) {
    if (!mask[start] || visited[start]) continue;
    let size = 0;
    let minCol = cols;
    let minRow = rows;
    let maxCol = -1;
    let maxRow = -1;
    stack.length = 0;
    stack.push(start);
    visited[start] = 1;
    while (stack.length) {
      const current = stack.pop();
      size += 1;
      const row = Math.floor(current / cols);
      const col = current % cols;
      if (col < minCol) minCol = col;
      if (row < minRow) minRow = row;
      if (col > maxCol) maxCol = col;
      if (row > maxRow) maxRow = row;
      for (let dy = -1; dy <= 1; dy += 1) {
        for (let dx = -1; dx <= 1; dx += 1) {
          if (!dx && !dy) continue;
          const nr = row + dy;
          const nc = col + dx;
          if (nr < 0 || nc < 0 || nr >= rows || nc >= cols) continue;
          const next = nr * cols + nc;
          if (mask[next] && !visited[next]) {
            visited[next] = 1;
            stack.push(next);
          }
        }
      }
    }
    const scored = scoreRect(minCol, minRow, maxCol, maxRow, size);
    if (scored && scored.score > bestScore) {
      bestScore = scored.score;
      best = scored;
    }
  }
  if (!best) return null;
  const marginX = (best.x1 - best.x0) * 0.10;
  const marginYTop = (best.y1 - best.y0) * 0.08;
  const marginYBottom = (best.y1 - best.y0) * 0.22;
  return {
    x0: clamp(best.x0 - marginX, 0, 1),
    y0: clamp(best.y0 - marginYTop, 0, 1),
    x1: clamp(best.x1 + marginX, 0, 1),
    y1: clamp(best.y1 + marginYBottom, 0, 1),
    goldRatio: best.goldRatio,
    fill: best.fill,
    areaRatio: best.areaRatio,
  };
}

function contiguousFastCorner(gray, width, x, y, threshold) {
  const center = gray[y * width + x];
  const offsets = [
    [0, -3], [1, -3], [2, -2], [3, -1], [3, 0], [3, 1], [2, 2], [1, 3],
    [0, 3], [-1, 3], [-2, 2], [-3, 1], [-3, 0], [-3, -1], [-2, -2], [-1, -3],
  ];
  let brighter = 0;
  let darker = 0;
  let bestBrighter = 0;
  let bestDarker = 0;
  let score = 0;
  // Repeat the first eight samples so runs spanning the circle boundary count.
  for (let index = 0; index < 24; index += 1) {
    const offset = offsets[index & 15];
    const value = gray[(y + offset[1]) * width + x + offset[0]];
    const delta = value - center;
    score = Math.max(score, Math.abs(delta));
    brighter = delta > threshold ? brighter + 1 : 0;
    darker = delta < -threshold ? darker + 1 : 0;
    bestBrighter = Math.max(bestBrighter, brighter);
    bestDarker = Math.max(bestDarker, darker);
    if (bestBrighter >= 9 || bestDarker >= 9) return score;
  }
  return 0;
}

function detectFeaturePoints(gray, width, height, roi, contrast) {
  const threshold = clamp(Math.round(11 + contrast * 0.10), 13, 30);
  const candidates = [];
  const startX = Math.max(4, roi.x0);
  const endX = Math.min(width - 4, roi.x1);
  const startY = Math.max(4, roi.y0);
  const endY = Math.min(height - 4, roi.y1);
  for (let y = startY; y < endY; y += 2) {
    for (let x = startX; x < endX; x += 2) {
      const score = contiguousFastCorner(gray, width, x, y, threshold);
      if (score) candidates.push({x, y, score});
    }
  }
  candidates.sort((left, right) => right.score - left.score);
  const kept = [];
  const radiusSquared = 42;
  for (const candidate of candidates) {
    let nearExisting = false;
    for (const point of kept) {
      const dx = point.x - candidate.x;
      const dy = point.y - candidate.y;
      if (dx * dx + dy * dy < radiusSquared) {
        nearExisting = true;
        break;
      }
    }
    if (!nearExisting) kept.push(candidate);
    if (kept.length >= 100) break;
  }
  return kept;
}

function skinOcclusionRatio(data, width, height, roi, tagMode) {
  const startX = Math.max(0, tagMode ? Math.round(width * 0.18) : Math.round(width * 0.22));
  const endX = Math.min(width, tagMode ? Math.round(width * 0.82) : Math.round(width * 0.78));
  const startY = Math.max(0, tagMode ? Math.round(height * 0.18) : Math.round(height * 0.20));
  const endY = Math.min(height, tagMode ? Math.round(height * 0.82) : Math.round(height * 0.80));
  let skin = 0;
  let total = 0;
  for (let y = startY; y < endY; y += 2) {
    for (let x = startX; x < endX; x += 2) {
      const index = (y * width + x) * 4;
      const r = data[index];
      const g = data[index + 1];
      const b = data[index + 2];
      const max = Math.max(r, g, b);
      const min = Math.min(r, g, b);
      const delta = max - min;
      const saturation = max ? delta / max : 0;
      const yLuma = 0.299 * r + 0.587 * g + 0.114 * b;
      const cb = 128 - 0.168736 * r - 0.331264 * g + 0.5 * b;
      const cr = 128 + 0.5 * r - 0.418688 * g - 0.081312 * b;
      const looksSkin =
        yLuma > 70 && yLuma < 245 &&
        delta > 18 &&
        // Real skin, even reddish/warm-toned, rarely exceeds ~0.5 HSV
        // saturation under normal lighting. Dyed plastic props (a bright
        // pink/magenta ring-display clip, for example) commonly land
        // inside the same YCbCr chroma range skin does but are far more
        // saturated -- without this, such a prop reads as "hand in frame"
        // and permanently blocks auto-capture even though nothing skin-
        // coloured is actually in the shot.
        saturation < 0.50 &&
        r > g && g > b * 0.55 &&
        cb >= 77 && cb <= 135 &&
        cr >= 133 && cr <= 190;
      if (looksSkin) skin += 1;
      total += 1;
    }
  }
  return total ? skin / total : 0;
}

function goldDominanceRatio(data, width, height, roi, tagMode, supportOverride) {
  const support = tagMode ? null : (supportOverride || findDarkSupportBounds(data, width, height, roi, tagMode));
  const startX = support ? Math.max(0, Math.round(support.x0 * width)) : Math.max(0, tagMode ? Math.round(width * 0.16) : Math.round(width * 0.20));
  const endX = support ? Math.min(width, Math.round(support.x1 * width)) : Math.min(width, tagMode ? Math.round(width * 0.84) : Math.round(width * 0.80));
  const startY = support ? Math.max(0, Math.round(support.y0 * height)) : Math.max(0, tagMode ? Math.round(height * 0.16) : Math.round(height * 0.18));
  const endY = support ? Math.min(height, Math.round(support.y1 * height)) : Math.min(height, tagMode ? Math.round(height * 0.84) : Math.round(height * 0.82));
  let gold = 0;
  let total = 0;
  for (let y = startY; y < endY; y += 2) {
    for (let x = startX; x < endX; x += 2) {
      const index = (y * width + x) * 4;
      const r = data[index];
      const g = data[index + 1];
      const b = data[index + 2];
      if (looksLikeMetal(r, g, b)) gold += 1;
      total += 1;
    }
  }
  return total ? gold / total : 0;
}

function goldBlobDominance(data, width, height, roi, tagMode, supportOverride) {
  const step = tagMode ? 4 : 3;
  const support = tagMode ? null : (supportOverride || findDarkSupportBounds(data, width, height, roi, tagMode));
  const startX = support ? Math.max(0, Math.round(support.x0 * width)) : Math.max(0, tagMode ? Math.round(width * 0.16) : Math.round(width * 0.18));
  const endX = support ? Math.min(width, Math.round(support.x1 * width)) : Math.min(width, tagMode ? Math.round(width * 0.84) : Math.round(width * 0.82));
  const startY = support ? Math.max(0, Math.round(support.y0 * height)) : Math.max(0, tagMode ? Math.round(height * 0.16) : Math.round(height * 0.18));
  const endY = support ? Math.min(height, Math.round(support.y1 * height)) : Math.min(height, tagMode ? Math.round(height * 0.84) : Math.round(height * 0.82));
  const cols = Math.max(1, Math.ceil((endX - startX) / step));
  const rows = Math.max(1, Math.ceil((endY - startY) / step));
  const mask = new Uint8Array(cols * rows);
  let warm = 0;
  let allMinCol = cols;
  let allMinRow = rows;
  let allMaxCol = -1;
  let allMaxRow = -1;

  function isWarmMetalAt(x, y) {
    const index = (y * width + x) * 4;
    const r = data[index];
    const g = data[index + 1];
    const b = data[index + 2];
    return looksLikeMetal(r, g, b);
  }

  for (let row = 0; row < rows; row += 1) {
    for (let col = 0; col < cols; col += 1) {
      const x = Math.min(width - 1, startX + col * step);
      const y = Math.min(height - 1, startY + row * step);
      if (isWarmMetalAt(x, y)) {
        mask[row * cols + col] = 1;
        warm += 1;
        if (col < allMinCol) allMinCol = col;
        if (row < allMinRow) allMinRow = row;
        if (col > allMaxCol) allMaxCol = col;
        if (row > allMaxRow) allMaxRow = row;
      }
    }
  }
  if (!warm) return {warmCoverage: 0, blobRatio: 0, bounds: null};

  const visited = new Uint8Array(mask.length);
  let largest = 0;
  let bestComponent = null;
  const stack = [];
  for (let start = 0; start < mask.length; start += 1) {
    if (!mask[start] || visited[start]) continue;
    let size = 0;
    let minCol = cols;
    let minRow = rows;
    let maxCol = -1;
    let maxRow = -1;
    stack.length = 0;
    stack.push(start);
    visited[start] = 1;
    while (stack.length) {
      const current = stack.pop();
      size += 1;
      const row = Math.floor(current / cols);
      const col = current % cols;
      if (col < minCol) minCol = col;
      if (row < minRow) minRow = row;
      if (col > maxCol) maxCol = col;
      if (row > maxRow) maxRow = row;
      for (let dy = -1; dy <= 1; dy += 1) {
        for (let dx = -1; dx <= 1; dx += 1) {
          if (!dx && !dy) continue;
          const nr = row + dy;
          const nc = col + dx;
          if (nr < 0 || nc < 0 || nr >= rows || nc >= cols) continue;
          const next = nr * cols + nc;
          if (mask[next] && !visited[next]) {
            visited[next] = 1;
            stack.push(next);
          }
        }
      }
    }
    if (size > largest) largest = size;
    const componentCenterX = (startX + ((minCol + maxCol + 1) * step / 2)) / width;
    const componentCenterY = (startY + ((minRow + maxRow + 1) * step / 2)) / height;
    const centerDistance = Math.abs(componentCenterX - 0.5) + Math.abs(componentCenterY - 0.5);
    const score = size * (1.25 - clamp(centerDistance, 0, 0.85));
    if (!bestComponent || score > bestComponent.score) {
      bestComponent = {score, size, minCol, minRow, maxCol, maxRow};
    }
  }
  // A recognised black tray card is already an object-level localiser, so
  // retain all gold pieces on that card (important for a matched pair). With
  // no card, select only the strongest central connected gold object instead
  // of spanning every gold-coloured object visible elsewhere in the tray.
  const selected = support ? {
    size: warm,
    minCol: allMinCol,
    minRow: allMinRow,
    maxCol: allMaxCol,
    maxRow: allMaxRow,
  } : bestComponent;
  if (!selected) return {warmCoverage: 0, blobRatio: 0, bounds: null};
  return {
    warmCoverage: selected.size / mask.length,
    blobRatio: largest / warm,
    bounds: {
      x0: clamp((startX + selected.minCol * step) / width, 0, 1),
      y0: clamp((startY + selected.minRow * step) / height, 0, 1),
      x1: clamp((startX + (selected.maxCol + 1) * step) / width, 0, 1),
      y1: clamp((startY + (selected.maxRow + 1) * step) / height, 0, 1),
    },
  };
}

function qualityInsideBounds(gray, width, height, bounds) {
  if (!bounds) return null;
  const boxWidth = Math.max(0.01, bounds.x1 - bounds.x0);
  const boxHeight = Math.max(0.01, bounds.y1 - bounds.y0);
  const x0 = clamp(Math.floor((bounds.x0 - boxWidth * 0.10) * width), 1, width - 2);
  const x1 = clamp(Math.ceil((bounds.x1 + boxWidth * 0.10) * width), 2, width - 1);
  const y0 = clamp(Math.floor((bounds.y0 - boxHeight * 0.10) * height), 1, height - 2);
  const y1 = clamp(Math.ceil((bounds.y1 + boxHeight * 0.10) * height), 2, height - 1);
  if (x1 - x0 < 6 || y1 - y0 < 6) return null;
  let lapTotal = 0;
  let lapSquared = 0;
  let clipped = 0;
  let measured = 0;
  for (let y = y0; y < y1; y += 1) {
    for (let x = x0; x < x1; x += 1) {
      const index = y * width + x;
      const value = gray[index];
      const laplacian = 4 * value - gray[index - 1] - gray[index + 1] -
        gray[index - width] - gray[index + width];
      lapTotal += laplacian;
      lapSquared += laplacian * laplacian;
      if (value <= 7 || value >= 248) clipped += 1;
      measured += 1;
    }
  }
  const lapMean = measured ? lapTotal / measured : 0;
  return {
    lapVariance: measured ? Math.max(0, lapSquared / measured - lapMean * lapMean) : 0,
    clippedRatio: measured ? clipped / measured : 1,
  };
}

function countPointsInRect(points, rect) {
  let count = 0;
  for (const point of points) {
    if (point.x >= rect.x0 && point.x <= rect.x1 && point.y >= rect.y0 && point.y <= rect.y1) {
      count += 1;
    }
  }
  return count;
}

function expandRect(rect, factor, guide) {
  const width = Math.max(0.001, rect.x1 - rect.x0);
  const height = Math.max(0.001, rect.y1 - rect.y0);
  const growX = width * Math.max(0, factor - 1) * 0.5;
  const growY = height * Math.max(0, factor - 1) * 0.5;
  return {
    x0: clamp(rect.x0 - growX, guide.x0, guide.x1),
    y0: clamp(rect.y0 - growY, guide.y0, guide.y1),
    x1: clamp(rect.x1 + growX, guide.x0, guide.x1),
    y1: clamp(rect.y1 + growY, guide.y0, guide.y1),
  };
}

function labelDetailRegion(rect, guide) {
  const centerX = (rect.x0 + rect.x1) / 2;
  const centerY = (rect.y0 + rect.y1) / 2;
  const width = Math.max(0.001, guide.x1 - guide.x0);
  const height = Math.max(0.001, guide.y1 - guide.y0);
  const horiz = centerX < guide.x0 + width / 3 ? 'left' : centerX > guide.x1 - width / 3 ? 'right' : 'centre';
  const vert = centerY < guide.y0 + height / 3 ? 'upper' : centerY > guide.y1 - height / 3 ? 'lower' : 'middle';
  if (vert === 'middle' && horiz === 'centre') return 'centre detail';
  if (vert === 'middle') return `${horiz} detail`;
  if (horiz === 'centre') return `${vert} detail`;
  return `${vert}-${horiz} detail`;
}

function buildShotPlan(data, width, height, points, pointBounds, goldBlob, goldRatio, goldDominant, tagMode) {
  const guide = tagMode
    ? {x0: 0.14, y0: 0.12, x1: 0.86, y1: 0.88}
    : {x0: 0.18, y0: 0.16, x1: 0.82, y1: 0.84};
  const mainBounds = !tagMode && goldBlob.bounds ? goldBlob.bounds : (pointBounds || guide);
  const mainWidth = Math.max(0.001, mainBounds.x1 - mainBounds.x0);
  const mainHeight = Math.max(0.001, mainBounds.y1 - mainBounds.y0);
  const searchRect = {
    x0: clamp(mainBounds.x0 - mainWidth * 0.08, guide.x0, guide.x1),
    y0: clamp(mainBounds.y0 - mainHeight * 0.08, guide.y0, guide.y1),
    x1: clamp(mainBounds.x1 + mainWidth * 0.08, guide.x0, guide.x1),
    y1: clamp(mainBounds.y1 + mainHeight * 0.08, guide.y0, guide.y1),
  };

  const cols = 3;
  const rows = 3;
  let bestCell = null;
  for (let row = 0; row < rows; row += 1) {
    for (let col = 0; col < cols; col += 1) {
      const cell = {
        x0: searchRect.x0 + (searchRect.x1 - searchRect.x0) * col / cols,
        x1: searchRect.x0 + (searchRect.x1 - searchRect.x0) * (col + 1) / cols,
        y0: searchRect.y0 + (searchRect.y1 - searchRect.y0) * row / rows,
        y1: searchRect.y0 + (searchRect.y1 - searchRect.y0) * (row + 1) / rows,
      };
      const pointCount = countPointsInRect(points, cell);
      const centerX = (cell.x0 + cell.x1) / 2;
      const centerY = (cell.y0 + cell.y1) / 2;
      const distanceFromCenter = Math.abs(centerX - ((mainBounds.x0 + mainBounds.x1) / 2)) +
        Math.abs(centerY - ((mainBounds.y0 + mainBounds.y1) / 2));
      const score = pointCount * 10 - distanceFromCenter * 12 + (row === 0 ? 1.5 : 0);
      if (!bestCell || score > bestCell.score) {
        bestCell = {rect: cell, score, pointCount};
      }
    }
  }

  if (!bestCell || bestCell.pointCount === 0) {
    bestCell = {
      rect: {
        x0: clamp(mainBounds.x0 + mainWidth * 0.20, guide.x0, guide.x1),
        y0: clamp(mainBounds.y0 + mainHeight * 0.20, guide.y0, guide.y1),
        x1: clamp(mainBounds.x1 - mainWidth * 0.20, guide.x0, guide.x1),
        y1: clamp(mainBounds.y1 - mainHeight * 0.20, guide.y0, guide.y1),
      },
      score: 0,
      pointCount: 0,
    };
  }

  const detailBounds = expandRect(bestCell.rect, 1.35, guide);
  const topBand = {
    x0: clamp((mainBounds.x0 + mainBounds.x1) / 2 - mainWidth * 0.22, guide.x0, guide.x1),
    x1: clamp((mainBounds.x0 + mainBounds.x1) / 2 + mainWidth * 0.22, guide.x0, guide.x1),
    y0: clamp(mainBounds.y0 - mainHeight * 0.18, guide.y0, guide.y1),
    y1: clamp(mainBounds.y0 + mainHeight * 0.16, guide.y0, guide.y1),
  };
  const topPoints = countPointsInRect(points, topBand);
  const studsConfidence = clamp((topPoints / 6) * 100, 0, 100);
  const studsLikely = !tagMode && topPoints >= 3 && studsConfidence >= 34;
  const mainCoverage = mainWidth * mainHeight;
  const frontZoom = clamp(
    mainCoverage < 0.14 ? 3.2 :
    mainCoverage < 0.22 ? 2.8 :
    mainCoverage < 0.34 ? 2.4 :
    mainCoverage < 0.48 ? 2.0 : 1.7,
    1.2, 4.0
  );
  const detailZoom = clamp(
    mainCoverage < 0.10 ? 4.0 :
    mainCoverage < 0.18 ? 3.6 :
    mainCoverage < 0.28 ? 3.0 : 2.5,
    1.6, 4.0
  );
  const detailLabel = labelDetailRegion(bestCell.rect, guide);
  const nextPhase = tagMode ? 'tag' : (studsLikely ? 'studs' : 'detail');
  const stepText = tagMode
    ? 'Tag next'
    : (studsLikely ? 'Studs likely' : 'Detail next');
  return {
    mainBounds,
    detailBounds,
    detailLabel,
    nextPhase,
    stepText,
    studsLikely,
    studsConfidence: Math.round(studsConfidence),
    frontZoom: Number(frontZoom.toFixed(1)),
    detailZoom: Number(detailZoom.toFixed(1)),
    coverage: Number(mainCoverage.toFixed(4)),
    goldRatio: Number(goldRatio.toFixed(4)),
    goldDominant: !!goldDominant,
  };
}

function analysePixels(imageData, kind, finalFrame) {
  const {data, width, height} = imageData;
  const gray = new Uint8Array(width * height);
  let total = 0;
  let totalSquared = 0;
  for (let pixel = 0, source = 0; pixel < gray.length; pixel += 1, source += 4) {
    const value = Math.round(data[source] * 0.299 + data[source + 1] * 0.587 + data[source + 2] * 0.114);
    gray[pixel] = value;
    total += value;
    totalSquared += value * value;
  }
  const mean = total / gray.length;
  const contrast = Math.sqrt(Math.max(0, totalSquared / gray.length - mean * mean));
  const tagMode = kind === 'tag';
  const roi = {
    x0: Math.round(width * (tagMode ? 0.08 : 0.15)),
    x1: Math.round(width * (tagMode ? 0.92 : 0.85)),
    y0: Math.round(height * (tagMode ? 0.15 : 0.15)),
    y1: Math.round(height * (tagMode ? 0.85 : 0.85)),
  };
  const support = tagMode ? null : findDarkSupportBounds(data, width, height, roi, tagMode);

  let lapTotal = 0;
  let lapSquared = 0;
  let measured = 0;
  let clipped = 0;
  for (let y = roi.y0 + 1; y < roi.y1 - 1; y += 1) {
    for (let x = roi.x0 + 1; x < roi.x1 - 1; x += 1) {
      const index = y * width + x;
      const value = gray[index];
      const laplacian = 4 * value - gray[index - 1] - gray[index + 1] -
        gray[index - width] - gray[index + width];
      lapTotal += laplacian;
      lapSquared += laplacian * laplacian;
      measured += 1;
      if (value <= 7 || value >= 248) clipped += 1;
    }
  }
  const lapMean = measured ? lapTotal / measured : 0;
  const lapVariance = measured ? Math.max(0, lapSquared / measured - lapMean * lapMean) : 0;
  const clippedRatio = measured ? clipped / measured : 1;
  const skinRatio = skinOcclusionRatio(data, width, height, roi, tagMode);
  const goldRatio = goldDominanceRatio(data, width, height, roi, tagMode, support);
  const goldBlob = goldBlobDominance(data, width, height, roi, tagMode, support);
  const goldDominant = !tagMode && (
    goldBlob.warmCoverage >= 0.06 && goldBlob.blobRatio >= 0.40
  );

  const previousKey = tagMode ? 'tag' : 'jewel';
  const previous = previousFrames.get(previousKey);
  let motion = null;
  if (!finalFrame && previous && previous.length === gray.length) {
    let difference = 0;
    for (let index = 0; index < gray.length; index += 2) {
      difference += Math.abs(gray[index] - previous[index]);
    }
    motion = difference / (Math.ceil(gray.length / 2) * 255);
  }
  if (!finalFrame) previousFrames.set(previousKey, gray);

  const points = detectFeaturePoints(gray, width, height, roi, contrast);
  const occupiedCells = new Set();
  const innerCells = new Set();
  const roiWidth = Math.max(1, roi.x1 - roi.x0);
  const roiHeight = Math.max(1, roi.y1 - roi.y0);
  for (const point of points) {
    const cellX = clamp(Math.floor((point.x - roi.x0) / roiWidth * 4), 0, 3);
    const cellY = clamp(Math.floor((point.y - roi.y0) / roiHeight * 4), 0, 3);
    occupiedCells.add(cellY * 4 + cellX);
    if (cellX >= 1 && cellX <= 2 && cellY >= 1 && cellY <= 2) {
      innerCells.add(cellY * 4 + cellX);
    }
  }
  let minPointX = 1;
  let minPointY = 1;
  let maxPointX = 0;
  let maxPointY = 0;
  for (const point of points) {
    const nx = point.x / width;
    const ny = point.y / height;
    if (nx < minPointX) minPointX = nx;
    if (ny < minPointY) minPointY = ny;
    if (nx > maxPointX) maxPointX = nx;
    if (ny > maxPointY) maxPointY = ny;
  }
  const pointBounds = points.length ? {
    x0: minPointX, y0: minPointY, x1: maxPointX, y1: maxPointY,
    width: Math.max(0, maxPointX - minPointX),
    height: Math.max(0, maxPointY - minPointY),
  } : null;
  const guideBox = tagMode
    ? {x0: 0.14, y0: 0.12, x1: 0.86, y1: 0.88}
    : {x0: 0.18, y0: 0.16, x1: 0.82, y1: 0.84};
  const boxMargin = tagMode ? 0.018 : 0.03;
  const goldBoundsUsable = !tagMode && !!goldBlob.bounds && (
    goldBlob.warmCoverage >= 0.02 || goldRatio >= 0.08 || goldDominant
  );
  const targetQuality = goldBoundsUsable
    ? qualityInsideBounds(gray, width, height, goldBlob.bounds)
    : null;
  const effectiveLapVariance = targetQuality ? targetQuality.lapVariance : lapVariance;
  const effectiveClippedRatio = targetQuality ? targetQuality.clippedRatio : clippedRatio;
  const fitBounds = goldBoundsUsable ? goldBlob.bounds : pointBounds;
  const boxFits = !!fitBounds &&
    fitBounds.x0 >= guideBox.x0 + boxMargin &&
    fitBounds.y0 >= guideBox.y0 + boxMargin &&
    fitBounds.x1 <= guideBox.x1 - boxMargin &&
    fitBounds.y1 <= guideBox.y1 - boxMargin;
  const boxFitScore = fitBounds ? clamp(
    Math.min(
      (fitBounds.x0 - guideBox.x0) / boxMargin,
      (fitBounds.y0 - guideBox.y0) / boxMargin,
      (guideBox.x1 - fitBounds.x1) / boxMargin,
      (guideBox.y1 - fitBounds.y1) / boxMargin
    ) * 100,
    0, 100
  ) : 0;

  const pointScore = clamp(points.length / (tagMode ? 35 : 55) * 100, 0, 100);
  const spreadScore = clamp(occupiedCells.size / (tagMode ? 6 : 9) * 100, 0, 100);
  const centerScore = points.length ? clamp(innerCells.size / (tagMode ? 3 : 5) * 100, 0, 100) : 0;
  const sharpnessScore = clamp((effectiveLapVariance - 20) / 170 * 100, 0, 100);
  const motionScore = finalFrame ? 100 : motion === null ? 0 : clamp((0.075 - motion) / 0.075 * 100, 0, 100);
  const exposureScore = clamp((0.20 - effectiveClippedRatio) / 0.20 * 100, 0, 100);
  const goldScore = clamp(
    goldBlob.warmCoverage * 140 + goldRatio * 55 + (goldDominant ? 12 : 0),
    0, 100
  );
  const capturePlan = buildShotPlan(data, width, height, points, pointBounds, goldBlob, goldRatio, goldDominant, tagMode);
  const score = Math.round(
    pointScore * 0.16 + spreadScore * 0.12 + centerScore * 0.18 +
    sharpnessScore * 0.36 + motionScore * 0.12 + exposureScore * 0.06
  );
  const jewelScore = Math.round(
    pointScore * 0.10 + spreadScore * 0.08 + centerScore * 0.08 +
    sharpnessScore * 0.34 + motionScore * 0.10 + exposureScore * 0.05 +
    goldScore * 0.25
  );
  const minimumPoints = tagMode ? 14 : 20;
  const minimumCells = tagMode ? 4 : 5;
  // Jewel capture gates on material detection alone -- is there a
  // well-localised gold/silver blob, is IT sharp, is the frame stable --
  // not framing/alignment/skin/glare heuristics layered on top. Those
  // extra checks (box-fit, point/cell counts, skin ratio, glare ratio)
  // each independently caused a real false-block this session: box-fit
  // fights live zoom's re-centering, skin ratio misfires on saturated
  // props (e.g. a pink display clip) that were never a hand, glare
  // misfires on legitimate diamond sparkle once zoomed in tight. None of
  // that is needed to know "the metal is in frame and it's sharp" --
  // looksLikeMetal() (gold OR silver) already does the material
  // identification; goldBoundsUsable means it found a real, sized blob.
  const metalPass = !tagMode && goldBoundsUsable &&
    sharpnessScore >= (finalFrame ? 48 : 46) &&
    (finalFrame || (motion !== null && motion <= 0.08));
  const pass = tagMode
    ? score >= (finalFrame ? 70 : 72) &&
      points.length >= minimumPoints && occupiedCells.size >= minimumCells &&
      centerScore >= 45 &&
      sharpnessScore >= 36 && effectiveClippedRatio < 0.20 &&
      (finalFrame || (motion !== null && motion <= 0.055))
    : metalPass;

  let reason = 'Hold steady';
  if (pass) reason = tagMode ? 'Tag clear' : 'Design clear';
  else if (tagMode && (points.length < minimumPoints || occupiedCells.size < minimumCells)) reason = 'Bring the tag into the guide';
  else if (tagMode && centerScore < 45) reason = 'Align the tag in the middle';
  else if (!tagMode && !goldBoundsUsable) reason = 'Show the gold/silver piece clearly';
  else if (sharpnessScore < (tagMode ? 36 : 46)) reason = 'Waiting for sharp focus';
  else if (tagMode && effectiveClippedRatio >= 0.20) reason = 'Reduce glare or deep shadow';
  else if (!finalFrame && motion === null) reason = 'Measuring stability';
  else if (!finalFrame && motion > (tagMode ? 0.055 : 0.08)) reason = 'Hold the device still';

  return {
    score,
    pass,
    reason,
    sharpness: Math.round(effectiveLapVariance),
    sharpnessScore: Math.round(sharpnessScore),
    motion: motion === null ? null : Number(motion.toFixed(4)),
    clippedRatio: Number(effectiveClippedRatio.toFixed(4)),
    frameClippedRatio: Number(clippedRatio.toFixed(4)),
    skinRatio: Number(skinRatio.toFixed(4)),
    goldRatio: Number(goldRatio.toFixed(4)),
    goldBlobCoverage: Number(goldBlob.warmCoverage.toFixed(4)),
    goldBlobRatio: Number(goldBlob.blobRatio.toFixed(4)),
    goldDominant,
    goldBounds: goldBlob.bounds,
    capturePlan,
    boxFitScore: Math.round(boxFitScore),
    boxFits,
    pointBounds,
    pointCount: points.length,
    occupiedCells: occupiedCells.size,
    centerCells: innerCells.size,
    points: points.map(point => ({
      x: point.x / width,
      y: point.y / height,
      strength: point.score,
    })),
  };
}

self.onmessage = event => {
  const {id, bitmap, kind, finalFrame} = event.data || {};
  if (!id || !bitmap) return;
  try {
    const maximum = finalFrame ? 720 : 360;
    const scale = Math.min(1, maximum / Math.max(bitmap.width, bitmap.height));
    const width = Math.max(1, Math.round(bitmap.width * scale));
    const height = Math.max(1, Math.round(bitmap.height * scale));
    if (!analysisCanvas || analysisCanvas.width !== width || analysisCanvas.height !== height) {
      analysisCanvas = new OffscreenCanvas(width, height);
    }
    const context = analysisCanvas.getContext('2d', {willReadFrequently: true});
    context.clearRect(0, 0, width, height);
    context.drawImage(bitmap, 0, 0, width, height);
    bitmap.close();
    const result = analysePixels(context.getImageData(0, 0, width, height), kind, !!finalFrame);
    self.postMessage({id, ok: true, result});
  } catch (error) {
    try { bitmap.close(); } catch (_) {}
    self.postMessage({id, ok: false, error: error && error.message ? error.message : String(error)});
  }
};
