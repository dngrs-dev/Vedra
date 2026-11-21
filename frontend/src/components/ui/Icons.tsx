interface IconProps {
  size?: number;
}

const base = (size: number) => ({
  width: size,
  height: size,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 2,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  'aria-hidden': true
});

export const SearchIcon = ({ size = 18 }: IconProps) => (
  <svg {...base(size)}><circle cx="11" cy="11" r="6.5" /><path d="m16 16 5 5" /></svg>
);
export const LayersIcon = ({ size = 18 }: IconProps) => (
  <svg {...base(size)}><path d="m12 3 9 5-9 5-9-5z" /><path d="m3 13 9 5 9-5" /></svg>
);
export const LocateIcon = ({ size = 18 }: IconProps) => (
  <svg {...base(size)}><circle cx="12" cy="12" r="3.5" /><path d="M12 2v4M12 18v4M2 12h4M18 12h4" /></svg>
);
export const FullscreenIcon = ({ size = 18 }: IconProps) => (
  <svg {...base(size)}><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" /></svg>
);
export const ChevronIcon = ({ size = 18 }: IconProps) => (
  <svg {...base(size)}><path d="m6 9 6 6 6-6" /></svg>
);
export const UserIcon = ({ size = 22 }: IconProps) => (
  <svg {...base(size)}><circle cx="12" cy="8" r="4" /><path d="M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7" /></svg>
);
export const BellIcon = ({ size = 22 }: IconProps) => (
  <svg {...base(size)}><path d="M6 17V11a6 6 0 1 1 12 0v6l2 2H4z" /><path d="M10 21h4" /></svg>
);
export const DropIcon = ({ size = 34 }: IconProps) => (
  <svg {...base(size)}><path d="M12 3s6 6.2 6 10.5A6 6 0 0 1 6 13.5C6 9.2 12 3 12 3z" /></svg>
);
export const CheckIcon = ({ size = 16 }: IconProps) => (
  <svg {...base(size)}><path d="m5 12 5 5 9-10" /></svg>
);
export const PrinterIcon = ({ size = 18 }: IconProps) => (
  <svg {...base(size)}><path d="M6 9V3h12v6M6 18H4v-7h16v7h-2" /><rect x="6" y="14" width="12" height="7" /></svg>
);
export const ArrowLeftIcon = ({ size = 18 }: IconProps) => (
  <svg {...base(size)}><path d="M19 12H5M11 6l-6 6 6 6" /></svg>
);

export function KowrLogo() {
  return (
    <div className="brand__logo" aria-hidden="true">
      <svg viewBox="0 0 64 28" width="64" height="28" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round">
        <path d="M2 14c12-12 36-12 60-2M2 19c12-10 34-10 56-2M2 24c10-8 30-8 48-2" />
      </svg>
      <span>Vedra</span>
    </div>
  );
}

/** Знак Vedra — три полоски из логотипа, без подписи; цвет берёт из currentColor */
export const VedraMark = ({ size = 48 }: IconProps) => (
  <svg viewBox="0 0 64 28" width={size} height={(size * 28) / 64} fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" aria-hidden="true">
    <path d="M2 14c12-12 36-12 60-2M2 19c12-10 34-10 56-2M2 24c10-8 30-8 48-2" />
  </svg>
);

export const PinIcon = ({ size = 24 }: IconProps) => (
  <svg {...base(size)}><path d="M12 21s7-6.2 7-11.5A7 7 0 0 0 5 9.5C5 14.8 12 21 12 21z" /><circle cx="12" cy="9.5" r="2.5" /></svg>
);
export const SproutIcon = ({ size = 24 }: IconProps) => (
  <svg {...base(size)}><path d="M12 21v-9" /><path d="M12 12c0-4 2.5-6 7-6 0 4.2-2.6 6-7 6z" /><path d="M12 14c0-3-2-4.8-6-4.8 0 3.4 2.2 4.8 6 4.8z" /></svg>
);
export const FileIcon = ({ size = 24 }: IconProps) => (
  <svg {...base(size)}><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5M9 13h6M9 17h6" /></svg>
);
export const ShieldIcon = ({ size = 24 }: IconProps) => (
  <svg {...base(size)}><path d="M12 3 5 6v5.5C5 16 8 19.6 12 21c4-1.4 7-5 7-9.5V6z" /><path d="m9 12 2.2 2.2L15.5 10" /></svg>
);
export const ArrowRightIcon = ({ size = 18 }: IconProps) => (
  <svg {...base(size)}><path d="M5 12h14M13 6l6 6-6 6" /></svg>
);
export const CalendarIcon = ({ size = 24 }: IconProps) => (
  <svg {...base(size)}><rect x="4" y="5" width="16" height="16" rx="2" /><path d="M4 10h16M8 3v4M16 3v4" /></svg>
);

export const HelpIcon = ({ size = 18 }: IconProps) => (
  <svg {...base(size)}><circle cx="12" cy="12" r="9" /><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.7.3-1 .9-1 1.7" /><path d="M12 17h.01" /></svg>
);
