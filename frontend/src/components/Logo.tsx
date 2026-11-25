import { cn } from '../lib/cn';

/**
 * Warden mark — the geometric W logo from Canva (assets/warden-logo-canva.pdf),
 * served from the frontend public dir as /warden-icon.png.
 * Bold black angular shapes (three diagonal bars + two squares), Mobbin-style.
 * Transparent background, so it sits clean on the white UI.
 */
export function WardenMark({ className, size = 36 }: { className?: string; size?: number }) {
  return (
    <img
      src="/warden-icon.png"
      alt="Warden logo"
      width={size}
      height={size}
      className={cn('shrink-0', className)}
    />
  );
}
