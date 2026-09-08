import test from 'node:test';
import assert from 'node:assert/strict';
import { normalizeRemoteState, calculateNewLine } from '../src/rates.js';

const snapshot = normalizeRemoteState({
  ok:true,
  published:{rate999:160000,rate24kt:161500,rate999Loaded:160200,rate22kt:152190,rate22ktWithGst:156755.7,unit:'per 10 g',status:'VERIFIED',confidence:100,at:Date.now(),variants:[{key:'18kt',label:'18KT',rate:123354}]},
  silver:{ok:true,published:{silverBase:180000,pure:185000,ornament:180375,unit:'per kg',status:'VERIFIED',confidence:100,at:Date.now()}}
},3);

test('22KT gold uses published business rate and GST',()=>{
  const x=calculateNewLine({metal:'gold',weight:10,purity:916},snapshot);
  assert.equal(x.rate,152190); assert.equal(x.metalValue,152190); assert.equal(x.gst,4565.7); assert.equal(x.total,156755.7);
});

test('silver 999 uses pure per-kg rate',()=>{
  const x=calculateNewLine({metal:'silver',weight:1000,purity:999},snapshot);
  assert.equal(x.rate,185000); assert.equal(x.metalValue,185000); assert.equal(x.total,190550);
});

test('18KT gold uses the published 750 variant',()=>{
  const x=calculateNewLine({metal:'gold',weight:10,purity:750},snapshot);
  assert.equal(x.rate,123354); assert.equal(x.metalValue,123354);
});

test('non-standard gold purity uses loaded 999 base',()=>{
  const x=calculateNewLine({metal:'gold',weight:10,purity:917},snapshot);
  assert.equal(x.rate,146903.4); assert.equal(x.metalValue,146903.4);
});

test('silver 975 uses ornament business rate',()=>{
  const x=calculateNewLine({metal:'silver',weight:1000,purity:975},snapshot);
  assert.equal(x.rate,180375); assert.equal(x.metalValue,180375);
});

test('non-standard silver purity scales from pure rate',()=>{
  const x=calculateNewLine({metal:'silver',weight:1000,purity:976},snapshot);
  assert.equal(x.rate,180740.74); assert.equal(x.metalValue,180740.74);
});
