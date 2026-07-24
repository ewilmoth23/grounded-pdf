export function Skeleton({ className = '', label }: { className?: string; label?: string }) {
  return (
    <div
      className={`relative overflow-hidden rounded-lg bg-ink-100 before:absolute before:inset-0 before:-translate-x-full before:animate-shimmer before:bg-gradient-to-r before:from-transparent before:via-white/60 before:to-transparent dark:bg-ink-800 dark:before:via-white/10 ${className}`}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      role={label ? 'status' : undefined}
    />
  );
}
