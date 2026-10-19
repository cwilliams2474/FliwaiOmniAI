export function Logo({ size = 26 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 26 26" aria-hidden="true">
      <circle cx="13" cy="13" r="11" fill="none" stroke="var(--accent)" strokeWidth="2.5" />
      <circle cx="13" cy="13" r="4" fill="var(--accent)" />
    </svg>
  );
}
