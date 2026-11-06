import full from '../assets/brand/logo.webp';
import horizontal from '../assets/brand/logo-horizontal.webp';
import mark from '../assets/brand/logo-mark.webp';

// The artwork comes from the brand logo. `full` is the stacked logo; at bar height its wordmark
// can't be read, so headers use `horizontal`, cut from the same art with the cloud moved beside it.
const ART = {
  full: { src: full, width: 640, height: 326 },
  horizontal: { src: horizontal, width: 607, height: 104 },
  mark: { src: mark, width: 214, height: 128 },
};

export function Logo({
  variant = 'horizontal',
  className = 'h-8 w-auto',
}: {
  variant?: keyof typeof ART;
  className?: string;
}) {
  return <img {...ART[variant]} alt="Karobar ERP" draggable={false} className={className} />;
}
