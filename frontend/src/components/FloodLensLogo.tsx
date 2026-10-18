import React from 'react';

interface FloodLensLogoProps extends React.SVGProps<SVGSVGElement> {
  variant?: 'full' | 'mark' | 'horizontal';
  showBackground?: boolean;
}

export const FloodLensLogo: React.FC<FloodLensLogoProps> = ({
  variant = 'horizontal',
  showBackground = false,
  className = 'h-10 w-auto',
  ...props
}) => {
  if (variant === 'mark') {
    return (
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 160 160"
        className={className}
        fill="none"
        {...props}
      >
        <defs>
          <linearGradient id="orbitCyanMark" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#38bdf8" />
            <stop offset="50%" stopColor="#06b6d4" />
            <stop offset="100%" stopColor="#0284c7" />
          </linearGradient>

          <linearGradient id="surgePulseMark" x1="0%" y1="100%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#0284c7" />
            <stop offset="45%" stopColor="#06b6d4" />
            <stop offset="75%" stopColor="#38bdf8" />
            <stop offset="100%" stopColor="#f43f5e" />
          </linearGradient>

          <linearGradient id="apertureGlowMark" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#38bdf8" stopOpacity="0.9" />
            <stop offset="100%" stopColor="#0284c7" stopOpacity="0.1" />
          </linearGradient>

          <radialGradient id="irisCoreMark" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#ffffff" />
            <stop offset="35%" stopColor="#67e8f9" />
            <stop offset="70%" stopColor="#0891b2" />
            <stop offset="100%" stopColor="#082f49" />
          </radialGradient>

          <filter id="bloomSoftMark" x="-30%" y="-30%" width="160%" height="160%">
            <feGaussianBlur stdDeviation="2.5" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>

          <filter id="laserGlowMark" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="4.5" result="blur2" />
            <feMerge>
              <feMergeNode in="blur2" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {showBackground && (
          <rect width="100%" height="100%" fill="#04060a" rx="12" />
        )}

        {/* Crosshairs */}
        <g stroke="#1e293b" strokeWidth="0.75" opacity="0.6">
          <line x1="80" y1="14" x2="80" y2="146" strokeDasharray="3 4" />
          <line x1="14" y1="80" x2="146" y2="80" strokeDasharray="3 4" />
          <circle cx="80" cy="80" r="66" fill="none" stroke="#0f172a" strokeWidth="1" />
        </g>

        {/* Reticles */}
        <path d="M 52 38 L 40 38 L 40 50" fill="none" stroke="#06b6d4" strokeWidth="1.75" strokeLinecap="round" />
        <path d="M 108 38 L 120 38 L 120 50" fill="none" stroke="#06b6d4" strokeWidth="1.75" strokeLinecap="round" />
        <path d="M 40 110 L 40 122 L 52 122" fill="none" stroke="#06b6d4" strokeWidth="1.75" strokeLinecap="round" />
        <path d="M 120 110 L 120 122 L 108 122" fill="none" stroke="#f43f5e" strokeWidth="1.75" strokeLinecap="round" />

        {/* Orbital Sweep */}
        <ellipse cx="80" cy="80" rx="55" ry="22" transform="rotate(-28 80 80)" fill="none" stroke="url(#orbitCyanMark)" strokeWidth="1.5" strokeDasharray="140 28 12 18" filter="url(#bloomSoftMark)" />

        {/* Lens Eye */}
        <path d="M 36 80 C 48 54, 112 54, 124 80 C 112 106, 48 106, 36 80 Z" fill="none" stroke="#0e7490" strokeWidth="1.25" opacity="0.8" />

        {/* Flood Crest Dynamic Arc */}
        <path d="M 42 79 C 55 58, 105 58, 118 79" fill="none" stroke="url(#surgePulseMark)" strokeWidth="3" strokeLinecap="round" filter="url(#bloomSoftMark)" />

        {/* Dual Frequency SAR Echo */}
        <path d="M 46 83 C 58 101, 102 101, 114 83" fill="none" stroke="url(#orbitCyanMark)" strokeWidth="2" strokeLinecap="round" strokeDasharray="32 6 8 4" />

        {/* Concentric Iso-Contours */}
        <path d="M 54 80 C 62 67, 98 67, 106 80 C 98 93, 62 93, 54 80 Z" fill="url(#apertureGlowMark)" stroke="#22d3ee" strokeWidth="0.75" strokeDasharray="2 3" />

        {/* Neural Optical Core */}
        <circle cx="80" cy="80" r="13" fill="url(#irisCoreMark)" filter="url(#laserGlowMark)" />
        <circle cx="80" cy="80" r="4.5" fill="#ffffff" />
        
        {/* Sweep Ray */}
        <line x1="80" y1="80" x2="119" y2="46" stroke="#e0f2fe" strokeWidth="1.5" strokeLinecap="round" />
        <circle cx="119" cy="46" r="2.2" fill="#38bdf8" filter="url(#bloomSoftMark)" />

        {/* Calibration Indices */}
        <circle cx="80" cy="27" r="1.5" fill="#06b6d4" />
        <circle cx="80" cy="133" r="1.5" fill="#0891b2" />
      </svg>
    );
  }

  // Full / Horizontal variant
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 760 160"
      className={className}
      fill="none"
      {...props}
    >
      <defs>
        <radialGradient id="spaceGazeH" cx="15%" cy="50%" r="80%">
          <stop offset="0%" stopColor="#0a101d" />
          <stop offset="60%" stopColor="#04060a" />
          <stop offset="100%" stopColor="#000000" />
        </radialGradient>

        <linearGradient id="orbitCyanH" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#38bdf8" />
          <stop offset="50%" stopColor="#06b6d4" />
          <stop offset="100%" stopColor="#0284c7" />
        </linearGradient>

        <linearGradient id="surgePulseH" x1="0%" y1="100%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#0284c7" />
          <stop offset="45%" stopColor="#06b6d4" />
          <stop offset="75%" stopColor="#38bdf8" />
          <stop offset="100%" stopColor="#f43f5e" />
        </linearGradient>

        <linearGradient id="apertureGlowH" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#38bdf8" stopOpacity="0.9" />
          <stop offset="100%" stopColor="#0284c7" stopOpacity="0.1" />
        </linearGradient>

        <radialGradient id="irisCoreH" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#ffffff" />
          <stop offset="35%" stopColor="#67e8f9" />
          <stop offset="70%" stopColor="#0891b2" />
          <stop offset="100%" stopColor="#082f49" />
        </radialGradient>

        <filter id="bloomSoftH" x="-30%" y="-30%" width="160%" height="160%">
          <feGaussianBlur stdDeviation="3.5" result="blur" />
          <feComposite in="SourceGraphic" in2="blur" operator="over" />
        </filter>

        <filter id="laserGlowH" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="6" result="blur2" />
          <feMerge>
            <feMergeNode in="blur2" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      {showBackground && (
        <rect width="100%" height="100%" fill="url(#spaceGazeH)" rx="12" />
      )}

      {/* Subtle Precision Geodetic Crosshairs */}
      <g stroke="#1e293b" strokeWidth="0.75" opacity="0.6">
        <line x1="86" y1="14" x2="86" y2="146" strokeDasharray="3 4" />
        <line x1="20" y1="80" x2="152" y2="80" strokeDasharray="3 4" />
        <circle cx="86" cy="80" r="66" fill="none" stroke="#0f172a" strokeWidth="1" />
      </g>

      {/* Logomark: The Orbital Flood Lens */}
      <g transform="translate(6, 0)">
        {/* Reticles */}
        <path d="M 52 38 L 40 38 L 40 50" fill="none" stroke="#06b6d4" strokeWidth="1.75" strokeLinecap="round" />
        <path d="M 108 38 L 120 38 L 120 50" fill="none" stroke="#06b6d4" strokeWidth="1.75" strokeLinecap="round" />
        <path d="M 40 110 L 40 122 L 52 122" fill="none" stroke="#06b6d4" strokeWidth="1.75" strokeLinecap="round" />
        <path d="M 120 110 L 120 122 L 108 122" fill="none" stroke="#f43f5e" strokeWidth="1.75" strokeLinecap="round" />

        {/* Orbital Lens Sweep Ring */}
        <ellipse cx="80" cy="80" rx="55" ry="22" transform="rotate(-28 80 80)" fill="none" stroke="url(#orbitCyanH)" strokeWidth="1.5" strokeDasharray="140 28 12 18" filter="url(#bloomSoftH)" />

        {/* Hydro-Optical Aperture */}
        <path d="M 36 80 C 48 54, 112 54, 124 80 C 112 106, 48 106, 36 80 Z" fill="none" stroke="#0e7490" strokeWidth="1.25" opacity="0.8" />

        {/* Flood Crest Dynamic Arc */}
        <path d="M 42 79 C 55 58, 105 58, 118 79" fill="none" stroke="url(#surgePulseH)" strokeWidth="3" strokeLinecap="round" filter="url(#bloomSoftH)" />

        {/* Dual Frequency SAR Echo */}
        <path d="M 46 83 C 58 101, 102 101, 114 83" fill="none" stroke="url(#orbitCyanH)" strokeWidth="2" strokeLinecap="round" strokeDasharray="32 6 8 4" />

        {/* Concentric Flood Level Iso-Contours */}
        <path d="M 54 80 C 62 67, 98 67, 106 80 C 98 93, 62 93, 54 80 Z" fill="url(#apertureGlowH)" stroke="#22d3ee" strokeWidth="0.75" strokeDasharray="2 3" />

        {/* Central Neural Optical Core */}
        <circle cx="80" cy="80" r="13" fill="url(#irisCoreH)" filter="url(#laserGlowH)" />
        <circle cx="80" cy="80" r="4.5" fill="#ffffff" />
        
        {/* Radar Vector Sweep Ray */}
        <line x1="80" y1="80" x2="119" y2="46" stroke="#e0f2fe" strokeWidth="1.5" strokeLinecap="round" />
        <circle cx="119" cy="46" r="2.2" fill="#38bdf8" filter="url(#bloomSoftH)" />

        {/* Elevation Calibration Indices */}
        <circle cx="80" cy="27" r="1.5" fill="#06b6d4" />
        <circle cx="80" cy="133" r="1.5" fill="#0891b2" />
      </g>

      {/* Typographic Wordmark */}
      <g transform="translate(168, 0)">
        {/* Primary Title: FLOODLENS */}
        <text
          x="0"
          y="93"
          fontFamily="'Barlow Condensed', 'D-DIN', 'Arial Narrow', sans-serif"
          fontSize="52"
          fontWeight="700"
          letterSpacing="4"
          fill="#ffffff"
        >
          FLOOD<tspan fill="#38bdf8">LENS</tspan>
        </text>

        {/* AI Multi-Mission Badge Container */}
        <g transform="translate(348, 51)">
          <rect x="0" y="0" width="62" height="46" rx="4" fill="#082f49" fillOpacity="0.45" stroke="#0284c7" strokeWidth="1.5" />
          
          <path d="M 0 8 L 0 0 L 8 0" fill="none" stroke="#38bdf8" strokeWidth="2" />
          <path d="M 54 46 L 62 46 L 62 38" fill="none" stroke="#38bdf8" strokeWidth="2" />

          <text
            x="31"
            y="32"
            fontFamily="'Barlow Condensed', 'D-DIN', 'Arial Narrow', sans-serif"
            fontSize="28"
            fontWeight="800"
            letterSpacing="2.5"
            textAnchor="middle"
            fill="#ffffff"
            filter="url(#bloomSoftH)"
          >
            AI
          </text>

          <circle cx="53" cy="9" r="2.5" fill="#f43f5e" filter="url(#bloomSoftH)" />
        </g>

        {/* Mission Eyebrow / Geospatial System Descriptor */}
        <text
          x="2"
          y="122"
          fontFamily="'Barlow Condensed', 'D-DIN', 'Arial Narrow', sans-serif"
          fontSize="10.5"
          fontWeight="600"
          letterSpacing="3.2"
          fill="#94a3b8"
        >
          PREDICT &amp; PROTECT <tspan fill="#0284c7">//</tspan> DETECT &amp; RESPOND <tspan fill="#0284c7">//</tspan> RETRAIN
        </text>

        {/* Precision Telemetry Line Element */}
        <line x1="2" y1="133" x2="408" y2="133" stroke="#1e293b" strokeWidth="1" />
        <line x1="2" y1="133" x2="78" y2="133" stroke="#06b6d4" strokeWidth="1.5" />
      </g>
    </svg>
  );
};

export default FloodLensLogo;
