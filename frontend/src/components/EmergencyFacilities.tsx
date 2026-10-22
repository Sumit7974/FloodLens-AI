import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  AlertTriangle,
  Building2,
  CheckCircle2,
  Filter,
  Hospital,
  MapPin,
  Phone,
  RefreshCw,
  Search,
  Shield,
  ShieldAlert,
  Users,
} from 'lucide-react';
import {
  DEMO_MODE,
  getShelters,
  getHospitals,
  type FacilityItem,
} from '../services/backendApi';
import type { BenchmarkScene } from '../types';
import { KOSHI_SHELTERS } from '../data/geospatialData';
import { GeospatialTerrainMap } from './map/GeospatialTerrainMap';

interface EmergencyFacilitiesProps {
  currentScene: BenchmarkScene;
}

export const EmergencyFacilities: React.FC<EmergencyFacilitiesProps> = ({ currentScene }) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [facilities, setFacilities] = useState<FacilityItem[]>([]);
  const [typeFilter, setTypeFilter] = useState<'all' | 'shelter' | 'hospital'>('all');
  const [verificationFilter, setVerificationFilter] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedFacility, setSelectedFacility] = useState<FacilityItem | null>(null);

  const fetchFacilities = useCallback(async () => {
    setLoading(true);
    setError(null);

    if (DEMO_MODE) {
      // In demo mode, provide verified demo facilities labeled as DEMO_LABELED
      const demoItems: FacilityItem[] = [
        ...KOSHI_SHELTERS.map((s) => ({
          id: s.id,
          type: 'shelter',
          name: s.name,
          verification_status: 'demo_labeled',
          capacity: s.capacity,
          contact_info: s.contact,
          status_checked_at: '2026-10-18T05:00:00Z',
          location: { type: 'Point' as const, coordinates: [s.coordinates[1], s.coordinates[0]] as [number, number] },
          longitude: s.coordinates[1],
          latitude: s.coordinates[0],
          source: 'Nepal EOC Historical Koshi Shelter Registry',
          details: { elevationMsl: s.elevationMsl, status: s.status, currentOccupancy: s.currentOccupancy },
          limitations: [
            'Demo-labeled reference record for authority simulation exercise.',
            'Structural safety must be re-confirmed with local ward office before public occupancy.',
          ],
        })),
        {
          id: 'hosp-bpkihs',
          type: 'hospital',
          name: 'BP Koirala Institute of Health Sciences (BPKIHS)',
          verification_status: 'verified',
          capacity: 450,
          contact_info: '+977 25-525555 (Emergency Triage)',
          status_checked_at: '2026-10-18T06:30:00Z',
          location: { type: 'Point' as const, coordinates: [87.28, 26.815] as [number, number] },
          longitude: 87.28,
          latitude: 26.815,
          source: 'Ministry of Health & Population - Disaster Liaison Hub',
          details: { trauma_beds: 45, flood_generator_active: true, heli_pad: true },
          limitations: [
            'Level 3 Tertiary Referral Hub; field ambulances must pre-notify triage coordinator.',
          ],
        },
        {
          id: 'hosp-inaruwa-dist',
          type: 'hospital',
          name: 'Inaruwa District Hospital Disaster Wing',
          verification_status: 'verified',
          capacity: 120,
          contact_info: '+977 25-560111',
          status_checked_at: '2026-10-18T06:00:00Z',
          location: { type: 'Point' as const, coordinates: [87.15, 26.6] as [number, number] },
          longitude: 87.15,
          latitude: 26.6,
          source: 'Sunsari District Health Office',
          details: { maternity_services: true, emergency_surge_beds: 30 },
          limitations: [
            'Ground-floor pharmacy threatened by local drainage backflow during crest periods.',
          ],
        },
        {
          id: 'hosp-barahakshetra-phc',
          type: 'hospital',
          name: 'Barahakshetra Primary Health Center',
          verification_status: 'unverified',
          capacity: 25,
          contact_info: 'Radio liaison only',
          status_checked_at: null,
          location: { type: 'Point' as const, coordinates: [87.14, 26.84] as [number, number] },
          longitude: 87.14,
          latitude: 26.84,
          source: 'Local Ward 2 Registry',
          details: { primary_care_only: true },
          limitations: [
            'UNVERIFIED: Staffing presence and medical tablet supplies have not been confirmed by health command.',
          ],
        },
      ];
      setFacilities(demoItems);
      setLoading(false);
      return;
    }

    try {
      const vFilter = verificationFilter === 'all' ? undefined : verificationFilter;
      const [shelterRes, hospitalRes] = await Promise.all([
        getShelters(vFilter).catch((err) => {
          console.warn('Shelters fetch failed:', err);
          return { count: 0, shelters: [] };
        }),
        getHospitals(vFilter).catch((err) => {
          console.warn('Hospitals fetch failed:', err);
          return { count: 0, hospitals: [] };
        }),
      ]);

      setFacilities([...shelterRes.shelters, ...hospitalRes.hospitals]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to query FastAPI facilities routes.');
    } finally {
      setLoading(false);
    }
  }, [verificationFilter]);

  useEffect(() => {
    void fetchFacilities();
  }, [fetchFacilities]);

  // Filter and search
  const filteredFacilities = useMemo(() => {
    return facilities.filter((f) => {
      if (typeFilter !== 'all' && f.type !== typeFilter) return false;
      if (verificationFilter !== 'all' && f.verification_status !== verificationFilter) return false;
      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase();
        const matchesName = f.name.toLowerCase().includes(query);
        const matchesContact = f.contact_info?.toLowerCase().includes(query);
        const matchesSource = f.source?.toLowerCase().includes(query);
        if (!matchesName && !matchesContact && !matchesSource) return false;
      }
      return true;
    });
  }, [facilities, typeFilter, verificationFilter, searchQuery]);

  const facilitiesWithCoordinates = useMemo(
    () => filteredFacilities.filter((f) => f.longitude != null && f.latitude != null),
    [filteredFacilities]
  );

  const facilitiesWithoutCoordinates = useMemo(
    () => filteredFacilities.filter((f) => f.longitude == null || f.latitude == null),
    [filteredFacilities]
  );

  const getVerificationBadge = (status: string) => {
    switch (status) {
      case 'verified':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 flex items-center gap-1">
            <CheckCircle2 className="w-3 h-3 text-emerald-400" />
            Verified Safe
          </span>
        );
      case 'demo_labeled':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-sky-500/20 text-sky-300 border border-sky-500/40 flex items-center gap-1">
            <Shield className="w-3 h-3 text-sky-400" />
            Demo Labeled
          </span>
        );
      case 'unverified':
      default:
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-rose-500/20 text-rose-300 border border-rose-500/40 flex items-center gap-1">
            <AlertTriangle className="w-3 h-3 text-rose-400" />
            Unverified
          </span>
        );
    }
  };

  return (
    <div className="space-y-4">
      {/* Mandatory Safety Notice */}
      <div className="p-3.5 rounded-lg bg-rose-500/10 border-2 border-rose-500/50 text-rose-200 text-xs font-mono flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2.5">
          <ShieldAlert className="w-4 h-4 text-rose-400 shrink-0" />
          <span>
            <strong>FACILITY SAFETY DISCLAIMER:</strong> Presence in this database does NOT guarantee operational safety, active medical staffing, or structural integrity. Never designate an unverified shelter as an authorized citizen evacuation safe-zone.
          </span>
        </div>
        <span className="px-2 py-0.5 rounded bg-black/60 border border-rose-400/40 text-[10px] text-rose-300 font-bold">
          AUTHORITY DIRECTORY ONLY
        </span>
      </div>

      {/* Header Bar */}
      <div className="p-4 rounded-lg bg-[#071326]/85 border border-[#1e3a5f]/80 shadow-[0_4px_20px_rgba(0,0,0,0.5)] backdrop-blur-xl flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded bg-emerald-500/20 border border-emerald-500/40 text-emerald-400">
            <Building2 className="w-5 h-5 text-emerald-400" />
          </div>
          <div>
            <h1 className="font-display text-base font-bold text-white tracking-[1.4px] uppercase flex items-center gap-2">
              Emergency Facilities // Shelters &amp; Hospital Registry
              <span className="px-2 py-0.5 rounded-full bg-emerald-500/15 border border-emerald-500/40 text-emerald-300 text-[9px] font-mono font-bold tracking-wider">
                API V1 FACILITIES
              </span>
            </h1>
            <p className="font-mono text-[10px] text-emerald-300 uppercase tracking-wider mt-0.5 font-semibold">
              GEOJSON REGISTER &bull; {currentScene.name}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            onClick={() => void fetchFacilities()}
            disabled={loading}
            className="px-3.5 py-1.5 rounded-md bg-[#0f2442] hover:bg-[#16355e] border border-[#2b4c7e] text-xs font-mono font-bold text-white flex items-center gap-1.5 transition-colors cursor-pointer disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-emerald-400 ${loading ? 'animate-spin' : ''}`} />
            <span>{loading ? 'Refreshing…' : 'Sync Registry'}</span>
          </button>
        </div>
      </div>

      {error && (
        <div className="p-3.5 rounded-lg bg-rose-500/15 border border-rose-500/40 text-rose-300 text-xs font-mono flex items-center gap-2">
          <ShieldAlert className="w-4 h-4 text-rose-400 shrink-0" />
          <span>Backend facility query error: {error}</span>
        </div>
      )}

      {/* Filter and Search Bar */}
      <div className="p-3.5 rounded-lg bg-[#071326]/85 border border-[#1e3a5f]/80 shadow-[0_4px_20px_rgba(0,0,0,0.5)] backdrop-blur-xl flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 font-mono text-xs">
        {/* Search Input */}
        <div className="relative flex-1 max-w-md">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by facility name, contact, or source..."
            className="w-full pl-9 pr-3 py-1.5 rounded-md bg-black/50 border border-[#1e3a5f] text-white text-xs placeholder:text-slate-500 focus:outline-none focus:border-emerald-500"
          />
        </div>

        {/* Filter Controls */}
        <div className="flex items-center gap-3 flex-wrap">
          {/* Facility Type Filter */}
          <div className="flex items-center gap-1 bg-black/40 p-1 rounded-md border border-[#1e3a5f]">
            {(['all', 'shelter', 'hospital'] as const).map((t) => (
              <button
                key={t}
                onClick={() => setTypeFilter(t)}
                className={`px-2.5 py-1 rounded text-[11px] font-bold uppercase transition-colors cursor-pointer ${
                  typeFilter === t
                    ? 'bg-emerald-500 text-black font-extrabold shadow'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                {t}
              </button>
            ))}
          </div>

          {/* Verification Status Filter */}
          <div className="flex items-center gap-1.5">
            <Filter className="w-3.5 h-3.5 text-slate-400" />
            <select
              value={verificationFilter}
              onChange={(e) => setVerificationFilter(e.target.value)}
              className="px-2.5 py-1.5 rounded-md bg-black/50 border border-[#1e3a5f] text-slate-200 text-xs focus:outline-none focus:border-emerald-500"
            >
              <option value="all">All Verification States</option>
              <option value="verified">Verified Only</option>
              <option value="unverified">Unverified Only</option>
              <option value="demo_labeled">Demo Labeled Only</option>
            </select>
          </div>
        </div>
      </div>

      {/* Geospatial Map Distribution Panel */}
      <div className="p-4 rounded-lg bg-[#071326]/85 border border-[#1e3a5f]/80 shadow-[0_4px_20px_rgba(0,0,0,0.5)] backdrop-blur-xl space-y-3 font-mono text-xs">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-2 border-b border-[#1e3a5f]">
          <div className="flex items-center gap-2">
            <MapPin className="w-4 h-4 text-emerald-400" />
            <h2 className="font-display text-xs font-bold text-white uppercase tracking-wider">
              Geospatial Facility Map Distribution // {currentScene.name}
            </h2>
          </div>
          <div className="flex items-center gap-2 flex-wrap text-[10px]">
            <span className="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-bold">
              {facilitiesWithCoordinates.length} Plotted (Valid Coordinates)
            </span>
            {facilitiesWithoutCoordinates.length > 0 && (
              <span className="px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30 font-bold">
                {facilitiesWithoutCoordinates.length} Omitted from Map (No Coordinates)
              </span>
            )}
          </div>
        </div>

        <GeospatialTerrainMap
          center={
            selectedFacility?.longitude != null && selectedFacility?.latitude != null
              ? [selectedFacility.longitude, selectedFacility.latitude]
              : currentScene.center || [87.05, 26.65]
          }
          zoom={11}
          pitch={45}
          bearing={-10}
          activeHorizon="Now"
          showInundation={true}
          showForecast={false}
          showGauges={false}
          showInfrastructure={true}
          showShelters={false}
          facilities={facilitiesWithCoordinates}
          onSelectFacility={(fac) => setSelectedFacility(fac)}
          height="320px"
        />

        <div className="flex items-center justify-between text-[10px] text-slate-400 flex-wrap gap-2 pt-1">
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 inline-block"></span>
              Verified
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-sky-500 inline-block"></span>
              Demo Labeled
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-rose-500 inline-block"></span>
              Unverified
            </span>
          </div>
          <span className="text-slate-500 italic">
            Markers added only when valid coordinates exist. Click marker or list card to inspect details.
          </span>
        </div>
      </div>

      {/* Facilities Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filteredFacilities.map((fac) => {
          const isHospital = fac.type === 'hospital';
          const hasCoords = fac.longitude != null && fac.latitude != null;

          return (
            <div
              key={fac.id}
              onClick={() => setSelectedFacility(fac)}
              className="p-4 rounded-lg bg-[#071326]/85 border border-[#1e3a5f]/80 hover:border-emerald-500/60 shadow-[0_4px_20px_rgba(0,0,0,0.5)] backdrop-blur-xl space-y-3 font-mono text-xs transition-all cursor-pointer flex flex-col justify-between"
            >
              <div className="space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <div className={`p-1.5 rounded ${isHospital ? 'bg-rose-500/20 text-rose-400' : 'bg-emerald-500/20 text-emerald-400'}`}>
                      {isHospital ? <Hospital className="w-4 h-4" /> : <Building2 className="w-4 h-4" />}
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-400 uppercase font-bold tracking-wider block">
                        {fac.type} &bull; {fac.id}
                      </span>
                      <h3 className="font-bold text-white text-sm leading-tight">
                        {fac.name}
                      </h3>
                    </div>
                  </div>
                </div>

                <div className="flex items-center justify-between pt-1">
                  {getVerificationBadge(fac.verification_status)}
                  <span className="text-[11px] text-slate-300 flex items-center gap-1 font-bold">
                    <Users className="w-3.5 h-3.5 text-cyan-400" />
                    {fac.capacity ? `${fac.capacity.toLocaleString()} ${isHospital ? 'Beds' : 'Persons'}` : 'Capacity Unrecorded'}
                  </span>
                </div>

                {/* Contact and Coordinates */}
                <div className="p-2 rounded bg-black/40 border border-[#1e3a5f]/60 space-y-1 text-[11px]">
                  <div className="flex items-center justify-between text-slate-300">
                    <span className="flex items-center gap-1 text-slate-400">
                      <Phone className="w-3 h-3 text-slate-400" />
                      Contact:
                    </span>
                    <span className="font-bold text-white">{fac.contact_info || 'Not provided'}</span>
                  </div>

                  <div className="flex items-center justify-between text-slate-300">
                    <span className="flex items-center gap-1 text-slate-400">
                      <MapPin className="w-3 h-3 text-slate-400" />
                      Coordinates:
                    </span>
                    <span className={hasCoords ? 'text-cyan-300 font-mono' : 'text-slate-500 italic'}>
                      {hasCoords ? `${fac.latitude?.toFixed(4)}, ${fac.longitude?.toFixed(4)}` : 'No valid coordinates'}
                    </span>
                  </div>
                </div>

                {/* Limitations and Caveats */}
                {fac.limitations && fac.limitations.length > 0 && (
                  <div className="p-2 rounded bg-amber-500/10 border border-amber-500/30 text-[10px] text-amber-200 space-y-0.5">
                    <span className="font-bold block uppercase tracking-wider text-[9px] text-amber-300">Caveat / Limitation:</span>
                    <p className="italic">{fac.limitations[0]}</p>
                  </div>
                )}
              </div>

              {/* Footer: Provenance & Freshness */}
              <div className="pt-2 border-t border-[#1e3a5f]/60 flex items-center justify-between text-[10px] text-slate-400">
                <span className="truncate max-w-[180px]" title={fac.source || 'Local Registry'}>
                  Source: {fac.source || 'Database'}
                </span>
                <span>
                  {fac.status_checked_at ? new Date(fac.status_checked_at).toLocaleDateString() : 'Unchecked'}
                </span>
              </div>
            </div>
          );
        })}

        {filteredFacilities.length === 0 && (
          <div className="col-span-full p-8 text-center rounded-lg bg-[#071326]/85 border border-[#1e3a5f] text-slate-400 font-mono text-xs">
            No emergency facilities matched the active type and verification criteria.
          </div>
        )}
      </div>

      {/* Facility Details Modal */}
      {selectedFacility && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-in fade-in">
          <div className="w-full max-w-lg rounded-lg bg-[#071326] border border-[#1e3a5f] p-6 shadow-2xl space-y-4 font-mono text-white text-xs">
            <div className="flex items-start justify-between">
              <div>
                <span className="text-[10px] text-slate-400 uppercase font-bold tracking-wider">
                  {selectedFacility.type} &bull; {selectedFacility.id}
                </span>
                <h3 className="font-display text-base font-bold text-white uppercase mt-0.5">
                  {selectedFacility.name}
                </h3>
              </div>
              {getVerificationBadge(selectedFacility.verification_status)}
            </div>

            <div className="p-3 bg-black/60 border border-[#1e3a5f] rounded space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-slate-400 font-bold uppercase text-[10px]">RECORDED CAPACITY:</span>
                <span className="font-bold text-white">
                  {selectedFacility.capacity ? `${selectedFacility.capacity} individuals / beds` : 'Not recorded in authority register'}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-400 font-bold uppercase text-[10px]">CONTACT CHANNEL:</span>
                <span className="text-cyan-300 font-bold">{selectedFacility.contact_info || 'No contact provided'}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-400 font-bold uppercase text-[10px]">GEOJSON POSITION:</span>
                <span className="font-mono text-white">
                  {selectedFacility.latitude != null && selectedFacility.longitude != null
                    ? `[Lat: ${selectedFacility.latitude}, Lon: ${selectedFacility.longitude}]`
                    : 'Coordinates unavailable'}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-400 font-bold uppercase text-[10px]">VERIFICATION TIMESTAMP:</span>
                <span className="text-slate-300">{selectedFacility.status_checked_at || 'Never verified'}</span>
              </div>
            </div>

            {selectedFacility.limitations && selectedFacility.limitations.length > 0 && (
              <div className="p-3 bg-amber-500/15 border border-amber-500/40 rounded space-y-1">
                <span className="text-[10px] font-bold text-amber-300 uppercase block">DATA LIMITATIONS &amp; SAFETY WARNINGS:</span>
                <ul className="list-disc list-inside text-[11px] text-amber-200 space-y-0.5">
                  {selectedFacility.limitations.map((lim, idx) => (
                    <li key={idx}>{lim}</li>
                  ))}
                </ul>
              </div>
            )}

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                onClick={() => setSelectedFacility(null)}
                className="px-4 py-1.5 rounded-md bg-[#0f2442] hover:bg-[#16355e] border border-[#2b4c7e] text-xs font-mono font-bold text-white transition-colors cursor-pointer"
              >
                Close Facility View
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
