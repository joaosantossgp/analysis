import { useEffect, useRef, useState, type RefObject } from "react";

/**
 * Track an element's content-box width with a ResizeObserver. Width drives the
 * SVG chart's pixel coordinate system so axis text and strokes stay crisp at
 * any container size (no viewBox scaling distortion). Height is caller-fixed.
 */
export function useElementWidth<T extends HTMLElement>(): [RefObject<T | null>, number] {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    // Seed synchronously so the first paint has a usable width.
    setWidth(el.clientWidth);
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const next = entry.contentRect.width;
        setWidth((prev) => (Math.abs(prev - next) > 0.5 ? next : prev));
      }
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return [ref, width];
}
