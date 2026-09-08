// Add 10 hero 3D products to products.json
const fs = require('fs');
const path = require('path');

const dataPath = path.join(__dirname, '..', 'assets', 'products.json');
const data = JSON.parse(fs.readFileSync(dataPath, 'utf8'));

const heroProducts = [
  {
    id: 'HERO-RING-001',
    label: 'HERO-RING-001',
    category: 'rings',
    categoryName: 'Rings',
    karat: 22,
    weight: 8.5,
    imageKey: 'HERO-RING-001',
    image: '',
    threeD: {
      glbUrl: 'asset:///assets/test-ring.glb',
      posterImageKey: null,
      materialVariants: [
        { id: 'yellow_22k', label: '22K Yellow Gold', metalColor: 'yellow', purity: 22, glbUrl: 'asset:///assets/test-ring.glb', hexAccent: '#D4A843' },
        { id: 'yellow_18k', label: '18K Yellow Gold', metalColor: 'yellow', purity: 18, glbUrl: 'asset:///assets/test-ring.glb', hexAccent: '#E0B85A' },
        { id: 'rose_18k', label: '18K Rose Gold', metalColor: 'rose', purity: 18, glbUrl: 'asset:///assets/test-ring.glb', hexAccent: '#C2907A' },
      ],
      purityOptions: [
        { karat: 22, label: '22K (916 Hallmark)', rateMultiplier: 1.0 },
        { karat: 18, label: '18K (750 Hallmark)', rateMultiplier: 0.75 },
      ],
      totalWeight: 8.5,
      stones: [],
      cameraPreset: { position: [0, 30, 60], target: [0, 0, 0], fov: 35, near: 0.1, far: 1000 },
      arEligible: true,
      availability: 'in_stock',
      lod: { low: 'asset:///assets/test-ring.glb', medium: 'asset:///assets/test-ring.glb', high: 'asset:///assets/test-ring.glb' },
      dimensions: { width: 25, height: 5, depth: 25 },
    },
  },
  {
    id: 'HERO-RING-002',
    label: 'HERO-RING-002',
    category: 'rings',
    categoryName: 'Rings',
    karat: 18,
    weight: 6.2,
    imageKey: 'HERO-RING-002',
    image: '',
    threeD: {
      glbUrl: 'asset:///assets/test-solitaire.glb',
      posterImageKey: null,
      materialVariants: [
        { id: 'yellow_18k', label: '18K Yellow Gold', metalColor: 'yellow', purity: 18, glbUrl: 'asset:///assets/test-solitaire.glb', hexAccent: '#E0B85A' },
        { id: 'white_18k', label: '18K White Gold', metalColor: 'white', purity: 18, glbUrl: 'asset:///assets/test-solitaire.glb', hexAccent: '#E8E8E8' },
      ],
      purityOptions: [
        { karat: 18, label: '18K (750 Hallmark)', rateMultiplier: 0.75 },
      ],
      totalWeight: 6.2,
      stones: [{ type: 'diamond', count: 1, totalCaratWeight: 0.5, clarity: 'VS1', setting: 'prong' }],
      cameraPreset: { position: [0, 35, 55], target: [0, 5, 0], fov: 35, near: 0.1, far: 1000 },
      arEligible: true,
      availability: 'in_stock',
      lod: { low: 'asset:///assets/test-solitaire.glb', medium: 'asset:///assets/test-solitaire.glb', high: 'asset:///assets/test-solitaire.glb' },
      dimensions: { width: 22, height: 20, depth: 22 },
    },
  },
  {
    id: 'HERO-RING-003',
    label: 'HERO-RING-003',
    category: 'rings',
    categoryName: 'Rings',
    karat: 22,
    weight: 10.1,
    imageKey: 'HERO-RING-003',
    image: '',
    threeD: {
      glbUrl: 'asset:///assets/test-filigree.glb',
      posterImageKey: null,
      materialVariants: [
        { id: 'yellow_22k', label: '22K Yellow Gold', metalColor: 'yellow', purity: 22, glbUrl: 'asset:///assets/test-filigree.glb', hexAccent: '#D4A843' },
      ],
      purityOptions: [
        { karat: 22, label: '22K (916 Hallmark)', rateMultiplier: 1.0 },
      ],
      totalWeight: 10.1,
      stones: [],
      cameraPreset: { position: [0, 30, 60], target: [0, 0, 0], fov: 35, near: 0.1, far: 1000 },
      arEligible: true,
      availability: 'made_to_order',
      lod: { low: 'asset:///assets/test-filigree.glb', medium: 'asset:///assets/test-filigree.glb', high: 'asset:///assets/test-filigree.glb' },
      dimensions: { width: 26, height: 5, depth: 26 },
    },
  },
  {
    id: 'HERO-EARR-001',
    label: 'HERO-EARR-001',
    category: 'jhumkas',
    categoryName: 'Jhumkas',
    karat: 22,
    weight: 12.4,
    imageKey: 'HERO-EARR-001',
    image: '',
    threeD: {
      glbUrl: 'asset:///assets/test-jhumka.glb',
      posterImageKey: null,
      materialVariants: [
        { id: 'yellow_22k', label: '22K Yellow Gold', metalColor: 'yellow', purity: 22, glbUrl: 'asset:///assets/test-jhumka.glb', hexAccent: '#D4A843' },
      ],
      purityOptions: [
        { karat: 22, label: '22K (916 Hallmark)', rateMultiplier: 1.0 },
      ],
      totalWeight: 12.4,
      stones: [],
      cameraPreset: { position: [0, 20, 50], target: [0, 5, 0], fov: 35, near: 0.1, far: 1000 },
      arEligible: true,
      availability: 'in_stock',
      lod: { low: 'asset:///assets/test-jhumka.glb', medium: 'asset:///assets/test-jhumka.glb', high: 'asset:///assets/test-jhumka.glb' },
      dimensions: { width: 12, height: 25, depth: 12 },
    },
  },
  {
    id: 'HERO-EARR-002',
    label: 'HERO-EARR-002',
    category: 'earrings',
    categoryName: 'Earrings',
    karat: 18,
    weight: 4.8,
    imageKey: 'HERO-EARR-002',
    image: '',
    threeD: {
      glbUrl: 'asset:///assets/test-stud-halo.glb',
      posterImageKey: null,
      materialVariants: [
        { id: 'white_18k', label: '18K White Gold', metalColor: 'white', purity: 18, glbUrl: 'asset:///assets/test-stud-halo.glb', hexAccent: '#E8E8E8' },
      ],
      purityOptions: [
        { karat: 18, label: '18K (750 Hallmark)', rateMultiplier: 0.75 },
      ],
      totalWeight: 4.8,
      stones: [{ type: 'diamond', count: 12, totalCaratWeight: 0.6, clarity: 'VS2', setting: 'prong' }],
      cameraPreset: { position: [0, 15, 40], target: [0, 0, 0], fov: 35, near: 0.1, far: 1000 },
      arEligible: true,
      availability: 'in_stock',
      lod: { low: 'asset:///assets/test-stud-halo.glb', medium: 'asset:///assets/test-stud-halo.glb', high: 'asset:///assets/test-stud-halo.glb' },
      dimensions: { width: 15, height: 15, depth: 5 },
    },
  },
  {
    id: 'HERO-BGL-001',
    label: 'HERO-BGL-001',
    category: 'bangle22',
    categoryName: 'Bangles',
    karat: 22,
    weight: 28.5,
    imageKey: 'HERO-BGL-001',
    image: '',
    threeD: {
      glbUrl: 'asset:///assets/test-bangle-plain.glb',
      posterImageKey: null,
      materialVariants: [
        { id: 'yellow_22k', label: '22K Yellow Gold', metalColor: 'yellow', purity: 22, glbUrl: 'asset:///assets/test-bangle-plain.glb', hexAccent: '#D4A843' },
      ],
      purityOptions: [
        { karat: 22, label: '22K (916 Hallmark)', rateMultiplier: 1.0 },
      ],
      totalWeight: 28.5,
      stones: [],
      cameraPreset: { position: [0, 25, 55], target: [0, 0, 0], fov: 35, near: 0.1, far: 1000 },
      arEligible: true,
      availability: 'in_stock',
      lod: { low: 'asset:///assets/test-bangle-plain.glb', medium: 'asset:///assets/test-bangle-plain.glb', high: 'asset:///assets/test-bangle-plain.glb' },
      dimensions: { width: 60, height: 4, depth: 60 },
    },
  },
  {
    id: 'HERO-BGL-002',
    label: 'HERO-BGL-002',
    category: 'bangle22',
    categoryName: 'Bangles',
    karat: 22,
    weight: 32.0,
    imageKey: 'HERO-BGL-002',
    image: '',
    threeD: {
      glbUrl: 'asset:///assets/test-bangle-studded.glb',
      posterImageKey: null,
      materialVariants: [
        { id: 'yellow_22k', label: '22K Yellow Gold', metalColor: 'yellow', purity: 22, glbUrl: 'asset:///assets/test-bangle-studded.glb', hexAccent: '#D4A843' },
      ],
      purityOptions: [
        { karat: 22, label: '22K (916 Hallmark)', rateMultiplier: 1.0 },
      ],
      totalWeight: 32.0,
      stones: [{ type: 'diamond', count: 16, totalCaratWeight: 0.8, clarity: 'SI1', setting: 'bezel' }],
      cameraPreset: { position: [0, 25, 55], target: [0, 0, 0], fov: 35, near: 0.1, far: 1000 },
      arEligible: false,
      availability: 'made_to_order',
      lod: { low: 'asset:///assets/test-bangle-studded.glb', medium: 'asset:///assets/test-bangle-studded.glb', high: 'asset:///assets/test-bangle-studded.glb' },
      dimensions: { width: 60, height: 4, depth: 60 },
    },
  },
  {
    id: 'HERO-PEND-001',
    label: 'HERO-PEND-001',
    category: 'pendants',
    categoryName: 'Pendants',
    karat: 22,
    weight: 5.2,
    imageKey: 'HERO-PEND-001',
    image: '',
    threeD: {
      glbUrl: 'asset:///assets/test-pendant.glb',
      posterImageKey: null,
      materialVariants: [
        { id: 'yellow_22k', label: '22K Yellow Gold', metalColor: 'yellow', purity: 22, glbUrl: 'asset:///assets/test-pendant.glb', hexAccent: '#D4A843' },
      ],
      purityOptions: [
        { karat: 22, label: '22K (916 Hallmark)', rateMultiplier: 1.0 },
      ],
      totalWeight: 5.2,
      stones: [],
      cameraPreset: { position: [0, 15, 40], target: [0, 2, 0], fov: 35, near: 0.1, far: 1000 },
      arEligible: true,
      availability: 'in_stock',
      lod: { low: 'asset:///assets/test-pendant.glb', medium: 'asset:///assets/test-pendant.glb', high: 'asset:///assets/test-pendant.glb' },
      dimensions: { width: 12, height: 18, depth: 5 },
    },
  },
  {
    id: 'HERO-NECK-001',
    label: 'HERO-NECK-001',
    category: 'necklaces',
    categoryName: 'Necklaces',
    karat: 22,
    weight: 45.0,
    imageKey: 'HERO-NECK-001',
    image: '',
    threeD: {
      glbUrl: 'asset:///assets/test-necklace.glb',
      posterImageKey: null,
      materialVariants: [
        { id: 'yellow_22k', label: '22K Yellow Gold', metalColor: 'yellow', purity: 22, glbUrl: 'asset:///assets/test-necklace.glb', hexAccent: '#D4A843' },
      ],
      purityOptions: [
        { karat: 22, label: '22K (916 Hallmark)', rateMultiplier: 1.0 },
      ],
      totalWeight: 45.0,
      stones: [],
      cameraPreset: { position: [0, 30, 80], target: [0, 5, 0], fov: 35, near: 0.1, far: 1000 },
      arEligible: false,
      availability: 'made_to_order',
      lod: { low: 'asset:///assets/test-necklace.glb', medium: 'asset:///assets/test-necklace.glb', high: 'asset:///assets/test-necklace.glb' },
      dimensions: { width: 36, height: 25, depth: 10 },
    },
  },
  {
    id: 'HERO-SET-001',
    label: 'HERO-SET-001',
    category: 'bridal sets',
    categoryName: 'Bridal Sets',
    karat: 22,
    weight: 70.0,
    imageKey: 'HERO-SET-001',
    image: '',
    threeD: {
      glbUrl: 'asset:///assets/test-bridal-set.glb',
      posterImageKey: null,
      materialVariants: [
        { id: 'yellow_22k', label: '22K Yellow Gold', metalColor: 'yellow', purity: 22, glbUrl: 'asset:///assets/test-bridal-set.glb', hexAccent: '#D4A843' },
      ],
      purityOptions: [
        { karat: 22, label: '22K (916 Hallmark)', rateMultiplier: 1.0 },
      ],
      totalWeight: 70.0,
      stones: [],
      cameraPreset: { position: [0, 35, 90], target: [0, 10, 0], fov: 35, near: 0.1, far: 1000 },
      arEligible: false,
      availability: 'made_to_order',
      lod: { low: 'asset:///assets/test-bridal-set.glb', medium: 'asset:///assets/test-bridal-set.glb', high: 'asset:///assets/test-bridal-set.glb' },
      dimensions: { width: 40, height: 35, depth: 15 },
    },
  },
];

// Add hero products (skip if already exists)
const existingIds = new Set(data.map(p => p.id));
let added = 0;
for (const hero of heroProducts) {
  if (!existingIds.has(hero.id)) {
    data.push(hero);
    added++;
  }
}

fs.writeFileSync(dataPath, JSON.stringify(data, null, 2));
console.log(`Added ${added} hero 3D products. Total: ${data.length}`);
