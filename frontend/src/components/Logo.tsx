import { cn } from '../lib/cn';
import { useTheme } from '../lib/theme';

/**
 * Warden mark — the geometric W logo from Canva (assets/warden-logo-canva.pdf),
 * served from the frontend public dir.
 * Bold black angular shapes (three diagonal bars + two squares), Mobbin-style.
 * Transparent background, so it sits clean on the UI.
 *
 * The mark swaps with the theme: the black mark on light mode, the white
 * mark (/warden-icon-white.png, same artwork in pure white) on dark mode.
 */
export function WardenMark({ className, size = 36 }: { className?: string; size?: number }) {
  const { resolved } = useTheme();
  const src = resolved === 'dark' ? '/warden-icon-white.png' : '/warden-icon.png';
  return (
    <img
      src={src}
      alt="Warden logo"
      width={size}
      height={size}
      className={cn('shrink-0', className)}
    />
  );
}
