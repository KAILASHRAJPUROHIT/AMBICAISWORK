/**
 * SINGLE SOURCE OF TRUTH — Aradhana_Master_Record.pdf (consolidated 22 Aug 2026).
 * Safe-to-hard-code section §37 only. Everything marked PENDING must stay
 * admin/CMS-configurable and must not ship as a final claim.
 */

export const MASTER = {
  legalName: 'Shree Aradhana Jewellers',
  displayName: 'Aradhana Jewellers',
  locationDescriptor: 'Aradhana Jewellers, Boisar',
  constitution: 'Proprietorship — Kesharsingh Rajpurohit',

  addressLines: [
    'Shop No. 48, Ostwal Empire,',
    'Arihant Market, Tarapur Road,',
    'Boisar, Palghar, Maharashtra 401501',
  ],
  shortAddress: 'Shop No. 48, Ostwal Empire, Boisar — 401501',

  phone: '+919422682086',
  whatsapp: 'https://wa.me/919422682086',
  email: 'info@aradhanajewellers.com',
  instagram: 'https://www.instagram.com/aradhanajewellers.boisar/',
  instagramHandle: '@aradhanajewellers.boisar',
  gstin: '27ACVPR5719A1Z9',
} as const;

/** §H Five open decisions — DO NOT resolve in code without Aradhana's call. */
export const PENDING = {
  /** 1992 KYC · 1995 brand material · 2003 trademark first-use */
  sinceYear: null as string | null,
  /** '#23519D' current working blue · '#003E7E' documented permanent blue */
  primaryBlue: '#23519D',
  /** Google vs Justdial schedules disagree — never compile timings */
  storeTimings: null as string[] | null,
  /** Facebook shows 89833 66647 — role undecided, never expose yet */
  secondaryPhone: null as string | null,
  /** No verified live public website — no website button allowed */
  websiteUrl: null as string | null,
} as const;

/** Tagline shown in-app until the year decision is locked. */
export const TAGLINE = PENDING.sinceYear
  ? `Trusted Since ${PENDING.sinceYear}`
  : ('Purity · Trust · Transparency' as string);

export const MAPS_URL =
  'https://maps.google.com/?q=Shree+Aradhana+Jewellers+Shop+48+Ostwal+Empire+Arihant+Market+Boisar+401501';
