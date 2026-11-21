/** Иллюстрация поля для hero (чистый SVG, без внешних картинок): небо, солнце, холмы, ряды посевов, капля. */
export function HeroArt() {
  const rows = Array.from({ length: 17 }, (_, i) => -320 + i * 72);
  return (
    <svg className="hero-art" viewBox="0 0 640 520" role="img" aria-label="Pole uprawne z kroplą wody" preserveAspectRatio="xMidYMid slice">
      <defs>
        <linearGradient id="ha-sky" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#dff0e6" />
          <stop offset="1" stopColor="#fff8e1" />
        </linearGradient>
        <radialGradient id="ha-sun" cx="50%" cy="50%" r="50%">
          <stop offset="0" stopColor="#ffe9a0" />
          <stop offset="1" stopColor="#ffe9a0" stopOpacity="0" />
        </radialGradient>
        <clipPath id="ha-clip"><rect width="640" height="520" rx="32" /></clipPath>
      </defs>
      <g clipPath="url(#ha-clip)">
        <rect width="640" height="520" fill="url(#ha-sky)" />
        <circle className="ha-glow" cx="470" cy="130" r="120" fill="url(#ha-sun)" />
        <circle className="ha-sun" cx="470" cy="130" r="44" fill="#f7d774" />
        <g fill="#fff" opacity=".9">
          <g className="ha-cloud ha-cloud--a"><ellipse cx="150" cy="120" rx="52" ry="16" /><ellipse cx="185" cy="108" rx="34" ry="14" /><ellipse cx="120" cy="110" rx="28" ry="12" /></g>
          <g className="ha-cloud ha-cloud--b"><ellipse cx="330" cy="70" rx="38" ry="11" /><ellipse cx="355" cy="62" rx="24" ry="10" /></g>
        </g>
        <path d="M0 300 C80 250 160 270 240 290 C340 315 420 240 520 262 C580 275 620 290 640 285 V520 H0Z" fill="#cfe6d4" />
        <path d="M0 345 C100 305 200 335 300 328 C400 322 500 292 640 332 V520 H0Z" fill="#a6d4b2" />
        <path d="M0 385 C160 352 480 352 640 385 V520 H0Z" fill="#5aa073" />
        <g className="ha-rows" stroke="#ffffff" strokeOpacity=".22" strokeWidth="3" fill="none">
          {rows.map((x) => <path key={x} d={`M320 360 L${x} 520`} />)}
        </g>
        <g fill="#2f6b4c" className="ha-trees">
          <rect x="88" y="318" width="6" height="26" rx="3" /><circle cx="91" cy="312" r="16" />
          <rect x="560" y="312" width="6" height="30" rx="3" /><circle cx="563" cy="304" r="19" />
        </g>
      </g>
      <g transform="translate(486 318)"><g className="ha-drop">
        <circle r="40" fill="#fff" />
        <circle r="40" fill="none" stroke="#e1ebe6" />
        <path d="M0 -20 C10 -7 15 0 15 7 A15 15 0 0 1 -15 7 C-15 0 -10 -7 0 -20Z" fill="#2f6fa8" />
        <path d="M-6 8 A7 7 0 0 0 0 14" stroke="#fff" strokeWidth="2.5" fill="none" strokeLinecap="round" />
      </g></g>
    </svg>
  );
}
