import { cn } from '@/lib/utils'

interface BrandLogoProps {
  className?: string
  /**
   * When true, renders without hover transition (useful for static contexts like cards).
   */
  static?: boolean
}

/**
 * Remnawave Admin brand mark — the "Halo Ring" signal logo.
 * Sources the shared /logo.svg (conic ring + pulse) so the mark stays
 * identical across the app, favicon and OG image.
 */
export function BrandLogo({ className, static: isStatic = false }: BrandLogoProps) {
  return (
    <img
      src="/logo.svg"
      alt="Remnawave Admin"
      draggable={false}
      className={cn(
        'select-none object-contain',
        !isStatic && 'transition-transform duration-300 ease-out hover:scale-105',
        className,
      )}
    />
  )
}
