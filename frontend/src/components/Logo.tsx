import { cn } from '../lib/cn';

/**
 * Warden mark — the approved Warden head icon (assets/icon-black.png),
 * served from the frontend public dir as /warden-icon.png.
 * A minimal black guardian head with two small horns. Clean and
 * professional like a modern SaaS logo — no pixel art, no game UI.
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
