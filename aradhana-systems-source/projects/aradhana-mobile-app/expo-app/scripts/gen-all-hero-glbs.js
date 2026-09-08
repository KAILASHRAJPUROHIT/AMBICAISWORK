// Generate test GLB files for all 10 hero designs
const fs = require('fs');
const path = require('path');

function pad4(buf) {
  const pad = (4 - (buf.length % 4)) % 4;
  if (pad === 0) return buf;
  const out = Buffer.alloc(buf.length + pad, 0x20);
  buf.copy(out);
  return out;
}
function writeFloats(arr) {
  const b = Buffer.alloc(arr.length * 4);
  arr.forEach((v, i) => b.writeFloatLE(v, i * 4));
  return b;
}
function writeUint32(arr) {
  const b = Buffer.alloc(arr.length * 4);
  arr.forEach((v, i) => b.writeUInt32LE(v, i * 4));
  return b;
}

function createTorus(R, r, segT, segR) {
  const positions = [], normals = [], indices = [];
  for (let j = 0; j <= segT; j++) {
    const u = (j / segT) * Math.PI * 2;
    for (let i = 0; i <= segR; i++) {
      const v = (i / segR) * Math.PI * 2;
      positions.push((R + r * Math.cos(v)) * Math.cos(u), r * Math.sin(v), (R + r * Math.cos(v)) * Math.sin(u));
      normals.push(Math.cos(v) * Math.cos(u), Math.sin(v), Math.cos(v) * Math.sin(u));
    }
  }
  for (let j = 0; j < segT; j++) for (let i = 0; i < segR; i++) {
    const a = j * (segR + 1) + i, b = a + segR + 1;
    indices.push(a, b, a + 1, b, b + 1, a + 1);
  }
  return { positions, normals, indices };
}

function createCylinder(radius, height, segments) {
  const positions = [], normals = [], indices = [];
  // Side
  for (let i = 0; i <= segments; i++) {
    const a = (i / segments) * Math.PI * 2;
    const x = Math.cos(a) * radius, z = Math.sin(a) * radius;
    positions.push(x, height / 2, z); normals.push(Math.cos(a), 0, Math.sin(a));
    positions.push(x, -height / 2, z); normals.push(Math.cos(a), 0, Math.sin(a));
  }
  for (let i = 0; i < segments; i++) {
    const a = i * 2, b = a + 1, c = a + 2, d = a + 3;
    indices.push(a, c, b, b, c, d);
  }
  // Top cap
  const topCenter = positions.length / 3;
  positions.push(0, height / 2, 0); normals.push(0, 1, 0);
  for (let i = 0; i <= segments; i++) {
    const a = (i / segments) * Math.PI * 2;
    positions.push(Math.cos(a) * radius, height / 2, Math.sin(a) * radius);
    normals.push(0, 1, 0);
  }
  for (let i = 0; i < segments; i++) {
    indices.push(topCenter, topCenter + 1 + i, topCenter + 2 + i);
  }
  // Bottom cap
  const botCenter = positions.length / 3;
  positions.push(0, -height / 2, 0); normals.push(0, -1, 0);
  for (let i = 0; i <= segments; i++) {
    const a = (i / segments) * Math.PI * 2;
    positions.push(Math.cos(a) * radius, -height / 2, Math.sin(a) * radius);
    normals.push(0, -1, 0);
  }
  for (let i = 0; i < segments; i++) {
    indices.push(botCenter, botCenter + 2 + i, botCenter + 1 + i);
  }
  return { positions, normals, indices };
}

function createSphere(radius, wSeg, hSeg) {
  const positions = [], normals = [], indices = [];
  for (let y = 0; y <= hSeg; y++) {
    const v = (y / hSeg) * Math.PI;
    for (let x = 0; x <= wSeg; x++) {
      const u = (x / wSeg) * Math.PI * 2;
      const px = -radius * Math.cos(u) * Math.sin(v);
      const py = radius * Math.cos(v);
      const pz = radius * Math.sin(u) * Math.sin(v);
      positions.push(px, py, pz);
      normals.push(px / radius, py / radius, pz / radius);
    }
  }
  for (let y = 0; y < hSeg; y++) for (let x = 0; x < wSeg; x++) {
    const a = y * (wSeg + 1) + x, b = a + wSeg + 1;
    indices.push(a, b, a + 1, b, b + 1, a + 1);
  }
  return { positions, normals, indices };
}

function mergeGeos(geos) {
  const pos = [], norm = [], idx = [];
  let offset = 0;
  for (const g of geos) {
    pos.push(...g.positions);
    norm.push(...g.normals);
    for (const i of g.indices) idx.push(i + offset);
    offset += g.positions.length / 3;
  }
  return { positions: pos, normals: norm, indices: idx };
}

function rotateX(geo, angle) {
  const c = Math.cos(angle), s = Math.sin(angle);
  const out = { positions: [], normals: [...geo.normals], indices: [...geo.indices] };
  for (let i = 0; i < geo.positions.length; i += 3) {
    const y = geo.positions[i + 1], z = geo.positions[i + 2];
    out.positions.push(geo.positions[i], y * c - z * s, y * s + z * c);
  }
  return out;
}

function rotateY(geo, angle) {
  const c = Math.cos(angle), s = Math.sin(angle);
  const out = { positions: [], normals: [...geo.normals], indices: [...geo.indices] };
  for (let i = 0; i < geo.positions.length; i += 3) {
    const x = geo.positions[i], z = geo.positions[i + 2];
    out.positions.push(x * c + z * s, geo.positions[i + 1], -x * s + z * c);
  }
  return out;
}

function translate(geo, tx, ty, tz) {
  const out = { positions: [], normals: [...geo.normals], indices: [...geo.indices] };
  for (let i = 0; i < geo.positions.length; i += 3) {
    out.positions.push(geo.positions[i] + tx, geo.positions[i + 1] + ty, geo.positions[i + 2] + tz);
  }
  return out;
}

function buildGLB(geo, material) {
  const posBuffer = writeFloats(geo.positions);
  const normBuffer = writeFloats(geo.normals);
  const idxBuffer = writeUint32(geo.indices);
  let minX = Infinity, minY = Infinity, minZ = Infinity;
  let maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity;
  for (let i = 0; i < geo.positions.length; i += 3) {
    minX = Math.min(minX, geo.positions[i]); minY = Math.min(minY, geo.positions[i + 1]); minZ = Math.min(minZ, geo.positions[i + 2]);
    maxX = Math.max(maxX, geo.positions[i]); maxY = Math.max(maxY, geo.positions[i + 1]); maxZ = Math.max(maxZ, geo.positions[i + 2]);
  }
  const binChunk = Buffer.concat([posBuffer, normBuffer, idxBuffer]);
  const binChunkPadded = pad4(binChunk);
  const json = {
    asset: { version: "2.0", generator: "aradhana-test" },
    scene: 0, scenes: [{ nodes: [0] }],
    nodes: [{ mesh: 0, name: "Model" }],
    meshes: [{ primitives: [{ attributes: { POSITION: 0, NORMAL: 1 }, indices: 2, material: 0 }] }],
    materials: [{ name: material.name, pbrMetallicRoughness: material.pbr, doubleSided: false }],
    accessors: [
      { bufferView: 0, componentType: 5126, count: geo.positions.length / 3, type: "VEC3", max: [maxX, maxY, maxZ], min: [minX, minY, minZ] },
      { bufferView: 1, componentType: 5126, count: geo.normals.length / 3, type: "VEC3" },
      { bufferView: 2, componentType: 5125, count: geo.indices.length, type: "SCALAR" },
    ],
    bufferViews: [
      { buffer: 0, byteOffset: 0, byteLength: posBuffer.length, target: 34962 },
      { buffer: 0, byteOffset: posBuffer.length, byteLength: normBuffer.length, target: 34962 },
      { buffer: 0, byteOffset: posBuffer.length + normBuffer.length, byteLength: idxBuffer.length, target: 34963 },
    ],
    buffers: [{ byteLength: binChunk.length }],
  };
  const jsonChunk = pad4(Buffer.from(JSON.stringify(json), 'utf8'));
  const totalLen = 12 + 8 + jsonChunk.length + 8 + binChunkPadded.length;
  const glb = Buffer.alloc(totalLen);
  let off = 0;
  glb.writeUInt32LE(0x46546C67, off); off += 4;
  glb.writeUInt32LE(2, off); off += 4;
  glb.writeUInt32LE(totalLen, off); off += 4;
  glb.writeUInt32LE(jsonChunk.length, off); off += 4;
  glb.writeUInt32LE(0x4E4F534A, off); off += 4;
  jsonChunk.copy(glb, off); off += jsonChunk.length;
  glb.writeUInt32LE(binChunkPadded.length, off); off += 4;
  glb.writeUInt32LE(0x004E4942, off); off += 4;
  binChunkPadded.copy(glb, off);
  return glb;
}

const gold22k = { name: "Gold_22K_Yellow", pbr: { baseColorFactor: [0.83, 0.66, 0.26, 1], metallicFactor: 0.95, roughnessFactor: 0.15 } };
const gold18k = { name: "Gold_18K_Yellow", pbr: { baseColorFactor: [0.85, 0.72, 0.35, 1], metallicFactor: 0.93, roughnessFactor: 0.18 } };
const goldRose = { name: "Gold_Rose", pbr: { baseColorFactor: [0.76, 0.55, 0.50, 1], metallicFactor: 0.92, roughnessFactor: 0.2 } };
const diamond = { name: "Diamond", pbr: { baseColorFactor: [0.95, 0.95, 0.98, 1], metallicFactor: 0.0, roughnessFactor: 0.02 } };

const outDir = path.join(__dirname, '..', 'assets');

// 1. Ring — classic band
const ring = rotateX(createTorus(10, 2.5, 64, 32), Math.PI / 2);
fs.writeFileSync(path.join(outDir, 'test-ring.glb'), buildGLB(ring, gold22k));

// 2. Ring — solitaire with stone
const solitaireBand = rotateX(createTorus(10, 2, 64, 32), Math.PI / 2);
const prong = translate(createCylinder(0.3, 6, 8), 0, 12, 0);
const stone = translate(createSphere(2.5, 16, 16), 0, 15, 0);
const solitaire = mergeGeos([solitaireBand, prong, stone]);
fs.writeFileSync(path.join(outDir, 'test-solitaire.glb'), buildGLB(solitaire, gold18k));

// 3. Ring — filigree (torus with bumps)
const filigree = rotateX(createTorus(10, 2.5, 64, 32), Math.PI / 2);
const bumps = [];
for (let i = 0; i < 12; i++) {
  const a = (i / 12) * Math.PI * 2;
  bumps.push(translate(createSphere(0.6, 8, 8), Math.cos(a) * 10, 2.5, Math.sin(a) * 10));
}
const filigreeFull = mergeGeos([filigree, ...bumps]);
fs.writeFileSync(path.join(outDir, 'test-filigree.glb'), buildGLB(filigreeFull, gold22k));

// 4. Earring — jhumka (bell shape: cone + sphere + dangling)
const bell = translate(rotateX(createCylinder(6, 10, 32), 0), 0, 5, 0);
const bellTop = translate(createCylinder(0.8, 8, 8), 0, 15, 0);
const bellBottom = translate(createSphere(1, 8, 8), 0, -1, 0);
const jhumka = mergeGeos([bell, bellTop, bellBottom]);
fs.writeFileSync(path.join(outDir, 'test-jhumka.glb'), buildGLB(jhumka, gold22k));

// 5. Earring — stud with halo
const studCenter = translate(createSphere(3, 16, 16), 0, 0, 0);
const haloRing = rotateX(createTorus(5, 0.8, 32, 16), Math.PI / 2);
const studHalo = mergeGeos([studCenter, haloRing]);
fs.writeFileSync(path.join(outDir, 'test-stud-halo.glb'), buildGLB(studHalo, diamond));

// 6. Bangle — plain gold
const bangle = rotateX(createTorus(12, 2, 64, 32), Math.PI / 2);
fs.writeFileSync(path.join(outDir, 'test-bangle-plain.glb'), buildGLB(bangle, gold22k));

// 7. Bangle — stone studded
const bangleBase = rotateX(createTorus(12, 2, 64, 32), Math.PI / 2);
const stones = [];
for (let i = 0; i < 16; i++) {
  const a = (i / 16) * Math.PI * 2;
  stones.push(translate(createSphere(0.8, 8, 8), Math.cos(a) * 12, 2, Math.sin(a) * 12));
}
const bangleStudded = mergeGeos([bangleBase, ...stones]);
fs.writeFileSync(path.join(outDir, 'test-bangle-studded.glb'), buildGLB(bangleStudded, gold22k));

// 8. Pendant — mangalsutra (oval + chain loop)
const pendantBody = translate(rotateY(createTorus(5, 1.5, 32, 16), Math.PI / 4), 0, 0, 0);
const pendantLoop = translate(createTorus(2, 0.5, 16, 8), 0, 7, 0);
const pendant = mergeGeos([pendantBody, pendantLoop]);
fs.writeFileSync(path.join(outDir, 'test-pendant.glb'), buildGLB(pendant, gold22k));

// 9. Necklace — short (multiple torus segments in arc)
const neckParts = [];
for (let i = 0; i < 12; i++) {
  const a = (i / 11) * Math.PI - Math.PI / 2;
  const seg = rotateX(createTorus(2, 0.8, 16, 8), Math.PI / 2);
  neckParts.push(translate(seg, Math.cos(a) * 18, Math.sin(a) * 18 + 10, 0));
}
const pendantDrop = translate(createTorus(4, 1.2, 32, 16), 0, -5, 0);
neckParts.push(pendantDrop);
const necklace = mergeGeos(neckParts);
fs.writeFileSync(path.join(outDir, 'test-necklace.glb'), buildGLB(necklace, gold22k));

// 10. Bridal set (necklace + 2 earrings combined)
const bridalNecklace = translate(necklace, 0, 15, 0);
const bridalEarring1 = translate(jhumka, -12, 5, 0);
const bridalEarring2 = translate(jhumka, 12, 5, 0);
const bridalSet = mergeGeos([bridalNecklace, bridalEarring1, bridalEarring2]);
fs.writeFileSync(path.join(outDir, 'test-bridal-set.glb'), buildGLB(bridalSet, gold22k));

console.log('All 10 hero test GLBs created in assets/');
fs.readdirSync(outDir).filter(f => f.startsWith('test-')).forEach(f => {
  const s = fs.statSync(path.join(outDir, f));
  console.log(`  ${f}: ${(s.size / 1024).toFixed(1)} KB`);
});
