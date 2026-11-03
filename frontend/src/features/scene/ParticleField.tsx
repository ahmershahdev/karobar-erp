import { useEffect, useRef } from 'react';
import {
  AdditiveBlending,
  BufferAttribute,
  BufferGeometry,
  Color,
  PerspectiveCamera,
  Points,
  Scene,
  ShaderMaterial,
  Vector2,
  WebGLRenderer,
} from 'three';

import { bars, globe, ring, seeds } from './shapes';
import { fragmentShader, vertexShader } from './shaders';

function token(name: string): Color {
  const value = getComputedStyle(document.documentElement).getPropertyValue(`--color-${name}`);
  return new Color(value.trim() || '#ffffff');
}

/**
 * Reads the scroll position against every element marked data-morph="0|1|2" and returns the
 * shape the field should be in: the marker nearest the middle of the screen wins, and between
 * two markers the value is interpolated so the morph follows the scroll exactly.
 */
function morphTarget(): number {
  const markers = Array.from(document.querySelectorAll<HTMLElement>('[data-morph]'));
  if (!markers.length) return 0;
  const middle = window.innerHeight / 2;
  const points = markers
    .map((el) => {
      const rect = el.getBoundingClientRect();
      return { at: rect.top + rect.height / 2 - middle, value: Number(el.dataset.morph) };
    })
    .sort((a, b) => a.at - b.at);
  const first = points[0];
  const last = points[points.length - 1];
  if (!first || !last) return 0;
  if (first.at >= 0) return first.value;
  if (last.at <= 0) return last.value;
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1];
    const b = points[i];
    if (a && b && a.at <= 0 && b.at >= 0) {
      return a.value + (b.value - a.value) * (-a.at / (b.at - a.at));
    }
  }
  return 0;
}

interface Props {
  animate: boolean;
  onFailure: () => void;
  // Which side of a wide screen the shape sits on, leaving the other side for content.
  side?: 'left' | 'right';
}

export default function ParticleField({ animate, onFailure, side = 'right' }: Props) {
  const hostRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    let renderer: WebGLRenderer;
    try {
      renderer = new WebGLRenderer({
        antialias: false,
        alpha: true,
        powerPreference: 'high-performance',
      });
    } catch {
      onFailure();
      return;
    }
    const small = window.matchMedia('(max-width: 768px), (pointer: coarse)').matches;
    const count = small ? 9000 : 22000;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, small ? 1.5 : 1.75));
    renderer.setClearColor(0x000000, 0);
    renderer.domElement.setAttribute('aria-hidden', 'true');
    renderer.domElement.style.width = '100%';
    renderer.domElement.style.height = '100%';
    host.append(renderer.domElement);

    const geometry = new BufferGeometry();
    geometry.setAttribute('position', new BufferAttribute(globe(count), 3));
    geometry.setAttribute('aBars', new BufferAttribute(bars(count), 3));
    geometry.setAttribute('aRing', new BufferAttribute(ring(count), 3));
    geometry.setAttribute('aSeed', new BufferAttribute(seeds(count), 1));

    const uniforms = {
      uTime: { value: 0 },
      uMorph: { value: 0 },
      uSize: { value: (small ? 9 : 7) * renderer.getPixelRatio() },
      uPointer: { value: new Vector2(10, 10) },
      uPointerStrength: { value: 0 },
      uOpacity: { value: 0 },
      uGold: { value: token('gold') },
      uPeach: { value: token('peach') },
      uCoral: { value: token('coral') },
      uLavender: { value: token('lavender') },
      uTurquoise: { value: token('turquoise') },
    };
    const material = new ShaderMaterial({
      vertexShader,
      fragmentShader,
      uniforms,
      transparent: true,
      depthWrite: false,
      blending: AdditiveBlending,
    });
    const points = new Points(geometry, material);
    const scene = new Scene();
    scene.add(points);
    const camera = new PerspectiveCamera(42, 1, 0.1, 50);
    camera.position.set(0, 0, 6.2);

    const pointer = new Vector2(10, 10);
    const tilt = new Vector2();
    let morph = morphTarget();
    let frame = 0;
    const start = performance.now();

    const resize = () => {
      const width = window.innerWidth;
      const height = window.innerHeight;
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      // Narrow screens pull the camera back so the whole shape stays in frame.
      camera.position.z = width < 768 ? 9.6 : 6.2;
      camera.updateProjectionMatrix();
      // On the left it shares its panel with a headline, so it sits smaller and up out of the way.
      points.position.x = width >= 1024 ? (side === 'left' ? -0.95 : 1.15) : 0;
      points.scale.setScalar(side === 'left' ? 0.72 : 1);
      points.position.y = width < 768 ? 1.9 : side === 'left' ? 0.85 : 0;
    };
    const onPointer = (event: PointerEvent) => {
      pointer.set(
        (event.clientX / window.innerWidth) * 2 - 1,
        -(event.clientY / window.innerHeight) * 2 + 1,
      );
    };
    const onLeave = () => pointer.set(10, 10);

    const render = (elapsed: number) => {
      morph += (morphTarget() - morph) * (animate ? 0.06 : 1);
      uniforms.uMorph.value = morph;
      uniforms.uTime.value = elapsed;
      // Full strength behind the hero, then dimmed so body text over it stays easy to read.
      const past = Math.min(1, Math.max(0, (window.scrollY / window.innerHeight - 0.3) / 0.6));
      const targetOpacity = 1 - 0.6 * past;
      uniforms.uOpacity.value += (targetOpacity - uniforms.uOpacity.value) * (animate ? 0.04 : 1);
      uniforms.uPointer.value.lerp(pointer, 0.12);
      uniforms.uPointerStrength.value +=
        ((pointer.x > 5 ? 0 : 1) - uniforms.uPointerStrength.value) * 0.08;
      tilt.lerp(pointer.x > 5 ? new Vector2() : pointer, 0.04);
      points.rotation.y = elapsed * 0.06 + tilt.x * 0.25 + morph * 0.6;
      points.rotation.x = 0.18 - tilt.y * 0.15 + (morph > 1 ? (morph - 1) * 0.9 : 0);
      renderer.render(scene, camera);
    };
    const loop = () => {
      if (!document.hidden) render((performance.now() - start) / 1000);
      frame = requestAnimationFrame(loop);
    };
    const still = () => render(4);

    resize();
    window.addEventListener('resize', resize);
    if (animate) {
      window.addEventListener('pointermove', onPointer, { passive: true });
      document.addEventListener('pointerleave', onLeave);
      loop();
    } else {
      window.addEventListener('scroll', still, { passive: true });
      window.addEventListener('resize', still);
      still();
    }

    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener('resize', resize);
      window.removeEventListener('resize', still);
      window.removeEventListener('scroll', still);
      window.removeEventListener('pointermove', onPointer);
      document.removeEventListener('pointerleave', onLeave);
      geometry.dispose();
      material.dispose();
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [animate, onFailure, side]);

  return <div ref={hostRef} className="absolute inset-0" />;
}
