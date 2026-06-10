import { useCallback, useEffect, useRef, useState, type RefCallback } from "react";

/**
 * Track an element's content-box width with a ResizeObserver. Width drives the
 * SVG chart's pixel coordinate system so axis text and strokes stay crisp at
 * any container size (no viewBox scaling distortion). Height is caller-fixed.
 */
export function useElementWidth<T extends HTMLElement>(): [RefCallback<T>, number] {
  const nodeRef = useRef<T | null>(null);
  const observerRef = useRef<ResizeObserver | null>(null);
  const [width, setWidth] = useState(0);

  const commitWidth = useCallback((next: number) => {
    setWidth((prev) => (Math.abs(prev - next) > 0.5 ? next : prev));
  }, []);

  const ref = useCallback(
    (node: T | null) => {
      observerRef.current?.disconnect();
      observerRef.current = null;
      nodeRef.current = node;

      if (!node) {
        commitWidth(0);
        return;
      }

      commitWidth(node.clientWidth);
      if (typeof ResizeObserver === "undefined") return;

      const observer = new ResizeObserver((entries) => {
        const next = entries[0]?.contentRect.width ?? node.clientWidth;
        commitWidth(next);
      });
      observer.observe(node);
      observerRef.current = observer;
    },
    [commitWidth],
  );

  useEffect(() => {
    if (typeof ResizeObserver !== "undefined") {
      return () => observerRef.current?.disconnect();
    }

    const handleResize = () => {
      if (nodeRef.current) commitWidth(nodeRef.current.clientWidth);
    };

    window.addEventListener("resize", handleResize);
    handleResize();
    return () => window.removeEventListener("resize", handleResize);
  }, [commitWidth]);

  return [ref, width];
}
