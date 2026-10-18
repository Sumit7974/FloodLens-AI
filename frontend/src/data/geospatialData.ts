export interface TelemetryGauge {
  id: string;
  name: string;
  river: string;
  coordinates: [number, number]; // [lat, lng]
  currentLevel: number;
  forecastLevels: {
    '1h': number;
    '3h': number;
    '6h': number;
  };
  warningThreshold: number;
  dangerThreshold: number;
  flowRate: number; // m3/s
  trend: 'RISING' | 'STABLE' | 'FALLING';
}

export interface InfrastructureItem {
  id: string;
  name: string;
  type: 'BRIDGE' | 'EMBANKMENT' | 'CANAL' | 'POWER';
  coordinates: [number, number];
  riskLevel: 'HIGH' | 'CRITICAL' | 'MODERATE';
  description: string;
}

export interface EvacuationShelter {
  id: string;
  name: string;
  coordinates: [number, number];
  capacity: number;
  currentOccupancy: number;
  elevationMsl: number;
  status: 'ACTIVE' | 'AT_CAPACITY' | 'THREATENED';
  contact: string;
}

export interface HorizonForecastDetails {
  horizon: '1h' | '3h' | '6h';
  label: string;
  severity: string;
  threatLevel: string;
  populationAtRisk: number;
  inundationAreaKm2: number;
  inflowCusecs: number;
  peakCrestEta: string;
  damGatesOpen: string;
  color: string;
  fillColor: string;
  highRiskWards: {
    name: string;
    depthRange: string;
    population: number;
    hazard: 'CRITICAL' | 'HIGH' | 'MODERATE';
  }[];
  // Multi-polygon coordinates around Koshi river basin [lat, lng]
  polygonCoords: [number, number][];
}

export const KOSHI_TELEMETRY_GAUGES: TelemetryGauge[] = [
  {
    id: 'gauge-chatara',
    name: 'Chatara Hydro-Station',
    river: 'Saptakoshi River (Main Stem)',
    coordinates: [26.839, 87.155],
    currentLevel: 8.18,
    forecastLevels: { '1h': 8.35, '3h': 8.54, '6h': 8.82 },
    warningThreshold: 6.8,
    dangerThreshold: 7.5,
    flowRate: 13240,
    trend: 'RISING',
  },
  {
    id: 'gauge-koshi-barrage',
    name: 'Koshi Barrage Main Sluice',
    river: 'Koshi International Reach',
    coordinates: [26.525, 86.932],
    currentLevel: 74.85,
    forecastLevels: { '1h': 74.98, '3h': 75.2, '6h': 75.45 },
    warningThreshold: 73.8,
    dangerThreshold: 74.5,
    flowRate: 12980,
    trend: 'RISING',
  },
  {
    id: 'gauge-mulghat',
    name: 'Mulghat Tamor Gauge',
    river: 'Tamor River Basin',
    coordinates: [26.935, 87.32],
    currentLevel: 6.42,
    forecastLevels: { '1h': 6.55, '3h': 6.7, '6h': 6.85 },
    warningThreshold: 5.8,
    dangerThreshold: 6.5,
    flowRate: 4120,
    trend: 'RISING',
  },
  {
    id: 'gauge-belka',
    name: 'Belka Confluence Post',
    river: 'Tribeni Confluence',
    coordinates: [26.785, 87.05],
    currentLevel: 7.62,
    forecastLevels: { '1h': 7.85, '3h': 8.15, '6h': 8.42 },
    warningThreshold: 6.9,
    dangerThreshold: 7.4,
    flowRate: 5180,
    trend: 'RISING',
  },
];

export const KOSHI_INFRASTRUCTURE: InfrastructureItem[] = [
  {
    id: 'infra-bridge',
    name: 'East-West Highway Bridge Approach',
    type: 'BRIDGE',
    coordinates: [26.612, 87.03],
    riskLevel: 'HIGH',
    description: 'High velocity scour threatening western approach abutment.',
  },
  {
    id: 'infra-spur-12',
    name: 'Koshi Eastern Embankment Spur km 12+400',
    type: 'EMBANKMENT',
    coordinates: [26.58, 86.975],
    riskLevel: 'CRITICAL',
    description: 'Imminent overtopping risk as discharge exceeds 420,000 cusecs.',
  },
  {
    id: 'infra-canal',
    name: 'Chatara Main Canal Intake',
    type: 'CANAL',
    coordinates: [26.83, 87.145],
    riskLevel: 'HIGH',
    description: 'Sediment surcharge and backflow flood hazard at headworks.',
  },
  {
    id: 'infra-grid',
    name: 'Inaruwa 132kV Substation Transmission Line',
    type: 'POWER',
    coordinates: [26.62, 87.12],
    riskLevel: 'MODERATE',
    description: 'Pylons 42-45 in agrarian floodplain reaching saturation.',
  },
];

export const KOSHI_SHELTERS: EvacuationShelter[] = [
  {
    id: 'sh-inaruwa',
    name: 'Inaruwa Municipality Safe Hub',
    coordinates: [26.602, 87.155],
    capacity: 1200,
    currentOccupancy: 480,
    elevationMsl: 82,
    status: 'ACTIVE',
    contact: '+977 25-560123',
  },
  {
    id: 'sh-bpkihs',
    name: 'BPKIHS Disaster Medical Outpost',
    coordinates: [26.815, 87.28],
    capacity: 800,
    currentOccupancy: 320,
    elevationMsl: 120,
    status: 'ACTIVE',
    contact: '+977 25-525555',
  },
  {
    id: 'sh-prakashpur',
    name: 'Prakashpur Primary School Refuge',
    coordinates: [26.705, 87.085],
    capacity: 650,
    currentOccupancy: 590,
    elevationMsl: 79,
    status: 'THREATENED',
    contact: '+977 981-4299881',
  },
  {
    id: 'sh-barahakshetra',
    name: 'Barahakshetra High-Ground Community Hall',
    coordinates: [26.845, 87.135],
    capacity: 900,
    currentOccupancy: 210,
    elevationMsl: 110,
    status: 'ACTIVE',
    contact: '+977 25-561990',
  },
];

export const HORIZON_FORECASTS: Record<'1h' | '3h' | '6h', HorizonForecastDetails> = {
  '1h': {
    horizon: '1h',
    label: '+1 Hour (Moderate Inflow)',
    severity: 'MODERATE / WATCH',
    threatLevel: 'Level 2: Accelerated Overbank',
    populationAtRisk: 9200,
    inundationAreaKm2: 28.4,
    inflowCusecs: 412000,
    peakCrestEta: '+1h 10m at Chatara',
    damGatesOpen: '34 of 56 Gates Opened',
    color: '#38bdf8',
    fillColor: '#0284c7',
    highRiskWards: [
      { name: 'Prakashpur (Ward 4 Lower)', depthRange: '0.6m – 1.1m', population: 3100, hazard: 'HIGH' },
      { name: 'Barahakshetra (Riverbank Corridor)', depthRange: '0.4m – 0.8m', population: 2800, hazard: 'MODERATE' },
      { name: 'Belka Riverside Settlements', depthRange: '0.5m – 0.9m', population: 3300, hazard: 'MODERATE' },
    ],
    polygonCoords: [
      [26.85, 87.15],
      [26.81, 87.17],
      [26.76, 87.13],
      [26.70, 87.10],
      [26.65, 87.05],
      [26.60, 87.01],
      [26.54, 86.95],
      [26.51, 86.92],
      [26.54, 86.90],
      [26.61, 86.95],
      [26.68, 87.00],
      [26.75, 87.06],
      [26.82, 87.11],
      [26.86, 87.13],
    ],
  },
  '3h': {
    horizon: '3h',
    label: '+3 Hours (High Flood Surge)',
    severity: 'HIGH / WARNING',
    threatLevel: 'Level 3: Major Embankment Pressure',
    populationAtRisk: 18420,
    inundationAreaKm2: 46.8,
    inflowCusecs: 448500,
    peakCrestEta: '+3h 15m at Spur 12+400',
    damGatesOpen: '42 of 56 Gates Opened',
    color: '#f97316',
    fillColor: '#ea580c',
    highRiskWards: [
      { name: 'Prakashpur (Wards 3 & 4)', depthRange: '1.4m – 2.0m', population: 5800, hazard: 'CRITICAL' },
      { name: 'Barahakshetra (Ward 2 Lowlands)', depthRange: '0.9m – 1.5m', population: 4200, hazard: 'HIGH' },
      { name: 'Gobargadha Sandbar Fringe', depthRange: '1.2m – 1.8m', population: 2100, hazard: 'HIGH' },
      { name: 'Bhokraha Narsingh (North-West)', depthRange: '0.7m – 1.3m', population: 6320, hazard: 'HIGH' },
    ],
    polygonCoords: [
      [26.88, 87.16],
      [26.83, 87.20],
      [26.77, 87.17],
      [26.71, 87.14],
      [26.64, 87.09],
      [26.57, 87.04],
      [26.50, 86.97],
      [26.47, 86.91],
      [26.52, 86.87],
      [26.62, 86.92],
      [26.70, 86.97],
      [26.79, 87.03],
      [26.87, 87.09],
    ],
  },
  '6h': {
    horizon: '6h',
    label: '+6 Hours (Severe / Peak Surge)',
    severity: 'CRITICAL / EMERGENCY',
    threatLevel: 'Level 4: Widespread Inundation & Breaches',
    populationAtRisk: 32800,
    inundationAreaKm2: 74.5,
    inflowCusecs: 472000,
    peakCrestEta: '+5h 45m Barrage Crest',
    damGatesOpen: '52 of 56 Gates Opened (Max Discharge)',
    color: '#e11d48',
    fillColor: '#be123c',
    highRiskWards: [
      { name: 'Prakashpur (All Low Wards)', depthRange: '2.1m – 2.9m', population: 8400, hazard: 'CRITICAL' },
      { name: 'Gobargadha Sandbar Island (Isolated)', depthRange: '2.4m – 3.2m', population: 3200, hazard: 'CRITICAL' },
      { name: 'Barahakshetra (Wards 1, 2 & 5)', depthRange: '1.6m – 2.4m', population: 7600, hazard: 'CRITICAL' },
      { name: 'Bhokraha Narsingh Floodplain', depthRange: '1.2m – 1.9m', population: 8100, hazard: 'HIGH' },
      { name: 'Inaruwa Municipality (Western Outskirts)', depthRange: '0.8m – 1.4m', population: 5500, hazard: 'HIGH' },
    ],
    polygonCoords: [
      [26.90, 87.17],
      [26.85, 87.23],
      [26.78, 87.21],
      [26.70, 87.18],
      [26.62, 87.14],
      [26.54, 87.09],
      [26.46, 87.01],
      [26.44, 86.89],
      [26.51, 86.84],
      [26.64, 86.88],
      [26.73, 86.93],
      [26.82, 87.00],
      [26.90, 87.08],
    ],
  },
};

export const HYDROGRAPH_TIMELINE = [
  { time: '-6h', label: '22:30 UTC', level: 6.85, flow: 8900, type: 'HISTORICAL' },
  { time: '-4h', label: '00:30 UTC', level: 7.20, flow: 10100, type: 'HISTORICAL' },
  { time: '-2h', label: '02:30 UTC', level: 7.68, flow: 11800, type: 'HISTORICAL' },
  { time: 'Now', label: '04:30 UTC', level: 8.18, flow: 13240, type: 'CURRENT' },
  { time: '+1h', label: '05:30 UTC', level: 8.35, flow: 13700, type: 'FORECAST' },
  { time: '+3h', label: '07:30 UTC', level: 8.54, flow: 14200, type: 'FORECAST' },
  { time: '+6h', label: '10:30 UTC', level: 8.82, flow: 14650, type: 'FORECAST' },
];

export const SATELLITE_COMPARISON_DATA = {
  scenes: {
    optical: {
      id: 'S2A_MSIL2A_20240814T044221_KOSHI',
      title: 'Sentinel-2 MSI (Optical NDWI/MNDWI)',
      resolution: '10-meter ground sampling',
      sensor: 'Multi-Spectral Instrument (Bands 3, 8, 11, 12)',
      cloudCover: '12%',
      waterIndex: 'Modified Normalized Difference Water Index (MNDWI > -0.05)',
      qualityTag: 'Cloud Mask Normalized via Fmask 4.0',
    },
    sar: {
      id: 'S1A_IW_GRDH_1SDV_20240814T003812_KOSHI',
      title: 'Sentinel-1 SAR (Radar Backscatter)',
      resolution: '10-meter pixel spacing',
      sensor: 'C-band Synthetic Aperture Radar (VV / VH Polarizations)',
      cloudCover: '0% (Cloud-Penetrating Active Microwave)',
      waterIndex: 'Lee Filtered Backscatter Thresholding (< -14.8 dB)',
      qualityTag: 'All-Weather Orbital Radar Calibrated',
    },
  },
  dates: {
    baseline: '2024-07-28 04:38 UTC (Pre-Monsoon Normal Riverbed)',
    inundation: '2024-08-14 04:42 UTC (Peak Monsoon Inundation Pass)',
  },
  statistics: {
    totalNewlyFloodedKm2: 64.2,
    floodedAgriculturalKm2: 41.8,
    submergedRoadsKm: 18.4,
    affectedSettlementsCount: 22,
    permanentWaterKm2: 18.2,
    estimatedDisplacedPeople: 14200,
  },
};
