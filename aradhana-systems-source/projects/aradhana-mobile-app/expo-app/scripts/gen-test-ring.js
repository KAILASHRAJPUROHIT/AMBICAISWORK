// Generate a test gold ring GLB binary file
// This creates a simple torus ring with PBR metallic-roughness material
const fs = require('fs');
const path = require('path');

// --- GLB builder helpers ---
function pad4(buf) {
  const pad = (4 - (buf.length % 4)) % 4;
  if (pad === 0) return buf;
  const out = Buffer.alloc(buf.length + pad, 0x20);
  buf.copy(out);
  return out;
}

function writeStr(s) {
  return Buffer.from(s, 'utf8');
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

// --- Generate torus vertices ---
function createTorus(R, r, segT, segR) {
  const positions = [];
  const normals = [];
  const indices = [];

  for (let j = 0; j <= segT; j++) {
    const u = (j / segT) * Math.PI * 2;
    for (let i = 0; i <= segR; i++) {
      const v = (i / segR) * Math.PI * 2;
      const x = (R + r * Math.cos(v)) * Math.cos(u);
      const y = r * Math.sin(v);
      const z = (R + r * Math.cos(v)) * Math.sin(u);
      positions.push(x, y, z);
      const nx = Math.cos(v) * Math.cos(u);
      const ny = Math.sin(v);
      const nz = Math.cos(v) * Math.sin(u);
      normals.push(nx, ny, nz);
    }
  }
  for (let j = 0; j < segT; j++) {
    for (let i = 0; i < segR; i++) {
      const a = j * (segR + 1) + i;
      const b = a + segR + 1;
      indices.push(a, b, a + 1, b, b + 1, a + 1);
    }
  }
  return { positions, normals, indices };
}

// Build ring: R=10 (major radius), r=2.5 (tube radius), rotated to sit flat
const torus = createTorus(10, 2.5, 64, 32);
// Rotate so ring lies flat on XZ plane (swap y and z)
const rotatedPos = [];
const rotatedNorm = [];
for (let i = 0; i < torus.positions.length; i += 3) {
  rotatedPos.push(torus.positions[i], torus.positions[i + 2], -torus.positions[i + 1]);
  rotatedNorm.push(torus.normals[i], torus.normals[i + 2], -torus.normals[i + 1]);
}

// --- Build the GLB ---
// We need: scene graph, mesh, buffer views, accessors, material, buffers

const posBuffer = writeFloats(rotatedPos);
const normBuffer = writeFloats(rotatedNorm);
const idxBuffer = writeUint32(torus.indices);

// Compute bounds
let minX = Infinity, minY = Infinity, minZ = Infinity;
let maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity;
for (let i = 0; i < rotatedPos.length; i += 3) {
  minX = Math.min(minX, rotatedPos[i]);
  minY = Math.min(minY, rotatedPos[i + 1]);
  minZ = Math.min(minZ, rotatedPos[i + 2]);
  maxX = Math.max(maxX, rotatedPos[i]);
  maxY = Math.max(maxY, rotatedPos[i + 1]);
  maxZ = Math.max(maxZ, rotatedPos[i + 2]);
}

const posMin = [minX, minY, minZ];
const posMax = [maxX, maxY, maxZ];

// GLB binary chunk: combine all buffer data
const totalIdxBytes = idxBuffer.length;
const posOffset = 0;
const normOffset = posBuffer.length;
const idxOffset = normOffset + normBuffer.length;
const binChunk = Buffer.concat([posBuffer, normBuffer, idxBuffer]);
// Pad to 4-byte alignment
const binChunkPadded = pad4(binChunk);

// JSON chunk (built as object references binary data)
const json = {
  asset: { version: "2.0", generator: "aradhana-test" },
  scene: 0,
  scenes: [{ nodes: [0] }],
  nodes: [{ mesh: 0, name: "Ring" }],
  meshes: [{
    primitives: [{
      attributes: { POSITION: 0, NORMAL: 1 },
      indices: 2,
      material: 0,
    }],
  }],
  materials: [{
    name: "Gold_22K_Yellow",
    pbrMetallicRoughness: {
      baseColorFactor: [0.83, 0.66, 0.26, 1.0],
      metallicFactor: 0.95,
      roughnessFactor: 0.15,
    },
    doubleSided: false,
  }],
  accessors: [
    {
      bufferView: 0,
      componentType: 5126, // FLOAT
      count: rotatedPos.length / 3,
      type: "VEC3",
      max: posMax,
      min: posMin,
    },
    {
      bufferView: 1,
      componentType: 5126,
      count: rotatedNorm.length / 3,
      type: "VEC3",
    },
    {
      bufferView: 2,
      componentType: 5125, // UNSIGNED_INT
      count: torus.indices.length,
      type: "SCALAR",
    },
  ],
  bufferViews: [
    { buffer: 0, byteOffset: posOffset, byteLength: posBuffer.length, target: 34962 },
    { buffer: 0, byteOffset: normOffset, byteLength: normBuffer.length, target: 34962 },
    { buffer: 0, byteOffset: idxOffset, byteLength: totalIdxBytes, target: 34963 },
  ],
  buffers: [{ byteLength: binChunk.length }],
};

const jsonStr = JSON.stringify(json);
const jsonChunk = pad4(Buffer.from(jsonStr, 'utf8'));

// GLB header: magic(4) + version(4) + length(4)
// JSON chunk: length(4) + type(4) + data
// BIN chunk: length(4) + type(4) + data
const headerLen = 12;
const jsonChunkLen = 8 + jsonChunk.length;
const binChunkLen = 8 + binChunkPadded.length;
const totalLen = headerLen + jsonChunkLen + binChunkLen;

const glb = Buffer.alloc(totalLen);
let off = 0;
glb.writeUInt32LE(0x46546C67, off); off += 4; // magic "glTF"
glb.writeUInt32LE(2, off); off += 4; // version
glb.writeUInt32LE(totalLen, off); off += 4; // total length

glb.writeUInt32LE(jsonChunk.length, off); off += 4; // JSON chunk length
glb.writeUInt32LE(0x4E4F534A, off); off += 4; // JSON type
jsonChunk.copy(glb, off); off += jsonChunk.length;

glb.writeUInt32LE(binChunkPadded.length, off); off += 4; // BIN chunk length
glb.writeUInt32LE(0x004E4942, off); off += 4; // BIN type
binChunkPadded.copy(glb, off); off += binChunkPadded.length;

const outPath = path.join(__dirname, '..', 'assets', 'test-ring.glb');
fs.writeFileSync(outPath, glb);
console.log(`Created ${outPath}: ${glb.length} bytes`);
console.log(`Vertices: ${rotatedPos.length / 3}, Triangles: ${torus.indices.length / 3}`);
