// Native transform/opacity animations avoid a JS animation loop and respect
// the OS motion preference. Callers cancel on replacement and unmount.
export function animate(
  element: HTMLElement,
  frames: Keyframe[],
  duration = 180,
): Animation | undefined {
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  return element.animate(frames, { duration, easing: 'cubic-bezier(.2,.7,.2,1)' });
}
