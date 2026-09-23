import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  GestureResponderEvent,
  StyleSheet,
  Text,
  TouchableWithoutFeedback,
  View,
} from 'react-native';
import { GLView, ExpoWebGLRenderingContext } from 'expo-gl';
import { Renderer } from 'expo-three';
import * as THREE from 'three';

// GLTFLoader and OrbitControls — three/examples ships without RN type mappings
// eslint-disable-next-line @typescript-eslint/no-require-imports
const { GLTFLoader } = require('three/examples/jsm/loaders/GLTFLoader');
// eslint-disable-next-line @typescript-eslint/no-require-imports
const { OrbitControls } = require('three/examples/jsm/controls/OrbitControls');

import type { Product, MaterialVariant, CameraPreset } from '@/services/products';
import { analytics } from '@/services/analytics';

// Three.js mutates a global instance — required for expo-three
(globalThis as any).THREE = (globalThis as any).THREE || THREE;

type Props = {
  product: Product;
  activeVariant?: MaterialVariant | null;
  onLoaded?: () => void;
  onError?: (err: Error) => void;
  style?: object;
};

type ViewerState = 'loading' | 'ready' | 'error';

type SceneState = {
  renderer: THREE.WebGLRenderer;
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  controls: any; // OrbitControls
  animationId: number;
  model: THREE.Group | null;
  idleTimer: ReturnType<typeof setTimeout> | null;
};

export default function JewelleryViewer({
  product,
  activeVariant,
  onLoaded,
  onError,
  style,
}: Props) {
  const [state, setState] = useState<ViewerState>('loading');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const sceneRef = useRef<SceneState | null>(null);

  const config = product.threeD;
  const glbUrl = activeVariant?.glbUrl ?? config?.glbUrl ?? null;
  const has3D = config !== null && glbUrl !== null;

  // Track 3D view started
  useEffect(() => {
    if (has3D && glbUrl) {
      analytics.track('3d_view_started', { productId: product.id, variant: activeVariant?.id });
    }
  }, [product.id, activeVariant?.id]);

  const resetCamera = useCallback(() => {
    const s = sceneRef.current;
    if (!s) return;
    const preset = config?.cameraPreset;
    if (preset) {
      s.camera.position.set(...preset.position);
      s.controls.target.set(...preset.target);
      s.camera.fov = preset.fov;
      s.camera.updateProjectionMatrix();
    }
    s.controls.reset();
  }, [config?.cameraPreset]);

  const handleDoubleTap = useCallback(
    (_e: GestureResponderEvent) => {
      resetCamera();
    },
    [resetCamera],
  );

  const onContextCreate = useCallback(
    (gl: ExpoWebGLRenderingContext) => {
      // ── Renderer ──
      const renderer = new Renderer({ gl }) as unknown as THREE.WebGLRenderer;
      renderer.setSize(gl.drawingBufferWidth, gl.drawingBufferHeight);
      renderer.setPixelRatio(1);
      renderer.outputColorSpace = THREE.SRGBColorSpace;
      renderer.toneMapping = THREE.ACESFilmicToneMapping;
      renderer.toneMappingExposure = 1.0;

      // ── Scene ──
      const scene = new THREE.Scene();
      scene.background = new THREE.Color(0xfaf8f5);

      // ── Camera ──
      const preset: CameraPreset = config?.cameraPreset ?? {
        position: [0, 30, 80],
        target: [0, 0, 0],
        fov: 35,
        near: 0.1,
        far: 1000,
      };
      const camera = new THREE.PerspectiveCamera(
        preset.fov,
        gl.drawingBufferWidth / gl.drawingBufferHeight,
        preset.near,
        preset.far,
      );
      camera.position.set(...preset.position);

      // ── Controls ──
      const controls = new OrbitControls(camera, gl.canvas as any);
      controls.target.set(...preset.target);
      controls.enableDamping = true;
      controls.dampingFactor = 0.08;
      controls.enablePan = false;
      controls.minDistance = 20;
      controls.maxDistance = 200;
      controls.autoRotate = true;
      controls.autoRotateSpeed = 2.0;
      controls.update();

      // ── Lighting ──
      const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
      scene.add(ambientLight);

      const keyLight = new THREE.DirectionalLight(0xfff5e6, 1.2);
      keyLight.position.set(50, 80, 60);
      keyLight.castShadow = false;
      scene.add(keyLight);

      const fillLight = new THREE.DirectionalLight(0xe6f0ff, 0.4);
      fillLight.position.set(-40, 30, -20);
      scene.add(fillLight);

      const rimLight = new THREE.DirectionalLight(0xffffff, 0.3);
      rimLight.position.set(0, -20, -50);
      scene.add(rimLight);

      // ── Ground reference ring ──
      const ringGeo = new THREE.RingGeometry(30, 50, 64);
      const ringMat = new THREE.MeshBasicMaterial({
        color: 0xe8d9a8,
        transparent: true,
        opacity: 0.15,
        side: THREE.DoubleSide,
      });
      const groundRing = new THREE.Mesh(ringGeo, ringMat);
      groundRing.rotation.x = -Math.PI / 2;
      groundRing.position.y = -0.5;
      scene.add(groundRing);

      // ── Load GLB ──
      let cancelled = false;
      const loader = new GLTFLoader();

      const disposeModel = (group: THREE.Group) => {
        group.traverse((child: THREE.Object3D) => {
          if (child instanceof THREE.Mesh) {
            child.geometry?.dispose();
            if (Array.isArray(child.material)) {
              child.material.forEach((m: THREE.Material) => m.dispose());
            } else {
              (child.material as THREE.Material)?.dispose();
            }
          }
        });
      };

      if (glbUrl) {
        loader.load(
          glbUrl,
          (gltf: any) => {
            if (cancelled) {
              disposeModel(gltf.scene);
              return;
            }

            const box = new THREE.Box3().setFromObject(gltf.scene);
            const center = box.getCenter(new THREE.Vector3());
            const size = box.getSize(new THREE.Vector3());
            const maxDim = Math.max(size.x, size.y, size.z);
            const scale = 60 / maxDim;
            gltf.scene.scale.setScalar(scale);
            gltf.scene.position.sub(center.multiplyScalar(scale));

            scene.add(gltf.scene);
            sceneRef.current = {
              renderer,
              scene,
              camera,
              controls,
              animationId: 0,
              model: gltf.scene,
              idleTimer: null,
            };
            setState('ready');
            onLoaded?.();
            analytics.track('3d_view_loaded', { productId: product.id, variant: activeVariant?.id });
          },
          undefined,
          (err: unknown) => {
            if (cancelled) return;
            const error = err instanceof Error ? err : new Error(String(err));
            setErrorMsg(error.message);
            setState('error');
            onError?.(error);
            analytics.track('3d_view_failed', { productId: product.id, error: error.message });
          },
        );
      }

      // ── Idle detection for auto-rotate ──
      const resetIdleTimer = () => {
        const s = sceneRef.current;
        if (!s) return;
        s.controls.autoRotate = false;
        if (s.idleTimer) clearTimeout(s.idleTimer);
        s.idleTimer = setTimeout(() => {
          if (sceneRef.current) {
            sceneRef.current.controls.autoRotate = true;
          }
        }, 3000);
      };

      // ── Animation loop ──
      let lastTime = 0;
      const animate = (time: number) => {
        if (cancelled) return;
        const delta = (time - lastTime) / 1000;
        lastTime = time;
        if (delta < 0.1) {
          controls.update();
        }
        renderer.render(scene, camera);
        gl.endFrameEXP();
        const id = requestAnimationFrame(animate);
        if (sceneRef.current) sceneRef.current.animationId = id;
      };
      const id = requestAnimationFrame(animate);
      if (sceneRef.current) sceneRef.current.animationId = id;

      // Expose for touch handler
      (gl as any)._resetIdle = resetIdleTimer;
    },
    [config?.cameraPreset, glbUrl, onLoaded, onError],
  );

  // ── Cleanup ──
  useEffect(() => {
    return () => {
      const s = sceneRef.current;
      if (!s) return;
      cancelAnimationFrame(s.animationId);
      if (s.idleTimer) clearTimeout(s.idleTimer);
      s.model?.traverse((child: THREE.Object3D) => {
        if (child instanceof THREE.Mesh) {
          child.geometry?.dispose();
          if (Array.isArray(child.material)) {
            child.material.forEach((m: THREE.Material) => m.dispose());
          } else {
            (child.material as THREE.Material)?.dispose();
          }
        }
      });
      s.controls.dispose();
      s.renderer.dispose();
      sceneRef.current = null;
    };
  }, []);

  // ── Variant switch ──
  useEffect(() => {
    if (!activeVariant || !sceneRef.current) return;
    analytics.track('variant_changed', { productId: product.id, variant: activeVariant.id });
    const s = sceneRef.current;
    const loader = new GLTFLoader();
    loader.load(activeVariant.glbUrl, (gltf: any) => {
      if (s.model) {
        s.scene.remove(s.model);
        s.model.traverse((child: THREE.Object3D) => {
          if (child instanceof THREE.Mesh) {
            child.geometry?.dispose();
            if (Array.isArray(child.material)) {
              child.material.forEach((m: THREE.Material) => m.dispose());
            } else {
              (child.material as THREE.Material)?.dispose();
            }
          }
        });
      }
      const box = new THREE.Box3().setFromObject(gltf.scene);
      const center = box.getCenter(new THREE.Vector3());
      const size = box.getSize(new THREE.Vector3());
      const maxDim = Math.max(size.x, size.y, size.z);
      const scale = 60 / maxDim;
      gltf.scene.scale.setScalar(scale);
      gltf.scene.position.sub(center.multiplyScalar(scale));
      s.scene.add(gltf.scene);
      s.model = gltf.scene;
    });
  }, [activeVariant]);

  return (
    <TouchableWithoutFeedback onPress={handleDoubleTap}>
      <View style={[styles.container, style]}>
        <GLView style={styles.glView} onContextCreate={onContextCreate} />
        {state === 'loading' && (
          <View style={styles.overlay}>
            <ActivityIndicator size="large" color="#C9A84C" />
            <Text style={styles.loadingText}>Loading 3D model...</Text>
          </View>
        )}
        {state === 'error' && (
          <View style={styles.overlay}>
            <Text style={styles.errorText}>3D view unavailable</Text>
            {errorMsg && (
              <Text style={styles.errorDetail} numberOfLines={2}>
                {errorMsg}
              </Text>
            )}
          </View>
        )}
      </View>
    </TouchableWithoutFeedback>
  );
}

const styles = StyleSheet.create({
  container: {
    width: '100%',
    aspectRatio: 1,
    borderRadius: 16,
    overflow: 'hidden',
    backgroundColor: '#FAF8F5',
  },
  glView: {
    flex: 1,
  },
  overlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: 'rgba(250, 248, 245, 0.9)',
    gap: 8,
  },
  loadingText: {
    fontSize: 13,
    color: '#9CA3AF',
    marginTop: 8,
  },
  errorText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#6B7280',
  },
  errorDetail: {
    fontSize: 12,
    color: '#9CA3AF',
    maxWidth: '80%',
    textAlign: 'center',
  },
});
