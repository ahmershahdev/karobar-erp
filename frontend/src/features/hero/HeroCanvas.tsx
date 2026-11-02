import { useEffect, useRef } from 'react';
import {
  Color,
  Mesh,
  OrthographicCamera,
  PlaneGeometry,
  Scene,
  ShaderMaterial,
  Vector2,
  WebGLRenderer,
} from 'three';

import { fragmentShader, vertexShader } from './silk-shader';

function token(name: string): Color {
  const value = getComputedStyle(document.documentElement).getPropertyValue(`--color-${name}`);
  return new Color(value.trim() || '#000000');
}

interface Props {
  animate: boolean;
  onFailure: () => void;
}

export default function HeroCanvas({ animate, onFailure }: Props) {
  const hostRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    let renderer: WebGLRenderer;
    try {
      renderer = new WebGLRenderer({ antialias: false, powerPreference: 'high-performance' });
    } catch {
      onFailure();
      return;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.75));
    renderer.domElement.setAttribute('aria-hidden', 'true');
    renderer.domElement.style.width = '100%';
    renderer.domElement.style.height = '100%';
    host.append(renderer.domElement);

    const uniforms = {
      uTime: { value: 0 },
      uResolution: { value: new Vector2() },
      uPointer: { value: new Vector2(0.5, 0.5) },
      uScroll: { value: 0 },
      uNavy: { value: token('navy') },
      uIndigo: { value: token('indigo') },
      uViolet: { value: token('violet') },
      uMagenta: { value: token('magenta') },
      uGold: { value: token('gold') },
      uTeal: { value: token('teal') },
      uBlack: { value: token('black') },
    };
    const material = new ShaderMaterial({ vertexShader, fragmentShader, uniforms });
    const geometry = new PlaneGeometry(2, 2);
    const scene = new Scene();
    scene.add(new Mesh(geometry, material));
    const camera = new OrthographicCamera(-1, 1, 1, -1, 0, 1);

    const target = new Vector2(0.5, 0.5);
    let visible = true;
    let frame = 0;
    const start = performance.now();
    if (!animate) uniforms.uTime.value = 12;

    const resize = () => {
      const { width, height } = host.getBoundingClientRect();
      renderer.setSize(width, height, false);
      renderer.getDrawingBufferSize(uniforms.uResolution.value);
      // setSize() clears the canvas; with no animation loop, nothing would redraw it.
      if (!animate) renderer.render(scene, camera);
    };
    const onPointer = (event: PointerEvent) => {
      const rect = host.getBoundingClientRect();
      target.set(
        (event.clientX - rect.left) / rect.width,
        1 - (event.clientY - rect.top) / rect.height,
      );
    };
    const onScroll = () => {
      uniforms.uScroll.value = Math.min(window.scrollY / window.innerHeight, 1);
    };
    const render = () => {
      uniforms.uTime.value = (performance.now() - start) / 1000;
      uniforms.uPointer.value.lerp(target, 0.05);
      renderer.render(scene, camera);
    };
    const loop = () => {
      if (visible && !document.hidden) render();
      frame = requestAnimationFrame(loop);
    };

    const observer = new IntersectionObserver(([entry]) => {
      visible = entry?.isIntersecting ?? false;
    });
    observer.observe(host);
    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(host);
    resize();

    if (animate) {
      window.addEventListener('pointermove', onPointer, { passive: true });
      window.addEventListener('scroll', onScroll, { passive: true });
      loop();
    }

    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      resizeObserver.disconnect();
      window.removeEventListener('pointermove', onPointer);
      window.removeEventListener('scroll', onScroll);
      geometry.dispose();
      material.dispose();
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [animate, onFailure]);

  return <div ref={hostRef} className="absolute inset-0" />;
}
