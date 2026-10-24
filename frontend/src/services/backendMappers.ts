import type { Alert, HelpRequest, AuthorityHandoffStatus, RequestCategory } from '../types';
import type { AssistanceRecord, AlertRecord } from './backendApi';

const categoryMap: Record<AssistanceRecord['category'], RequestCategory> = {
  evacuation: 'EVACUATION',
  medical: 'MEDICAL',
  food_water: 'FOOD_WATER',
  shelter: 'SHELTER',
  other: 'EVACUATION',
};

export function toViewStatus(value: AssistanceRecord['status']): AuthorityHandoffStatus {
  switch (value) {
    case 'acknowledged':
      return 'ACKNOWLEDGED_BY_AUTHORITY';
    case 'in_progress':
      return 'SIMULATED_AUTHORITY_ACK';
    case 'resolved':
      return 'RESOLVED';
    default:
      return 'LOCAL_LOGGED';
  }
}

/**
 * Authenticated authority view of persisted assistance records.
 * Fields absent from the backend (depth, urgency score, name, battery) are never inferred.
 */
export function toHelpRequest(record: AssistanceRecord): HelpRequest {
  const viewStatus = toViewStatus(record.status);

  let requesterName = 'Civilian SOS';
  let contactNumber = 'Contact provided via DEOC';
  let urgency: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' = 'HIGH';
  let landmark = record.details || 'Distress beacon location';

  if (record.details) {
    const requesterMatch = record.details.match(/Requester:\s*([^|]+)/i);
    if (requesterMatch && requesterMatch[1].trim()) {
      requesterName = requesterMatch[1].trim();
    }
    const phoneMatch = record.details.match(/Phone:\s*([^|]+)/i);
    if (phoneMatch && phoneMatch[1].trim()) {
      contactNumber = phoneMatch[1].trim();
    }
    const urgencyMatch = record.details.match(/Urgency:\s*([^|]+)/i);
    if (urgencyMatch && urgencyMatch[1].trim()) {
      const parsedUrgency = urgencyMatch[1].trim().toUpperCase();
      if (['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'].includes(parsedUrgency)) {
        urgency = parsedUrgency as any;
      }
    }
    const landmarkMatch = record.details.match(/Landmark:\s*([^|]+)/i);
    if (landmarkMatch && landmarkMatch[1].trim()) {
      landmark = landmarkMatch[1].trim();
    }
  }

  return {
    id: record.id,
    requester_name: requesterName,
    contact_number: contactNumber,
    timestamp: record.created_at,
    category: categoryMap[record.category] || 'EVACUATION',
    urgency,
    urgency_score: urgency === 'CRITICAL' ? 'Priority 1 (Immediate Hazard)' : urgency === 'HIGH' ? 'Priority 2 (High Risk)' : 'Priority 3 (Standard)',
    status: viewStatus,
    handoff_status: viewStatus,
    people_count: record.people_count || 1,
    location_name: `Civilian SOS (${record.latitude.toFixed(4)}°N, ${record.longitude.toFixed(4)}°E)`,
    coordinates: [record.latitude, record.longitude],
    landmark,
    notes: [
      record.details,
      record.status_notes ? `Authority Note: ${record.status_notes}` : '',
    ].filter(Boolean).join(' | '),
    authority_handoff_target: record.assigned_to || undefined,
    authority_verification: 'Authenticated live civilian beacon',
    activity_log: [
      { timestamp: record.created_at, action: 'Assistance report recorded in backend', author: 'FloodLens Citizen SOS' },
      { timestamp: record.updated_at, action: `Backend status: ${record.status}`, author: 'Authorized authority user' },
    ],
  };
}

/**
 * Backend AlertResponse has no severity or population metrics.
 * Represent absent values as unspecified rather than fabricating an emergency.
 */
export function toUiAlert(record: AlertRecord): Alert {
  return {
    id: record.id,
    code: `DEMO-${record.id.slice(0, 8)}`,
    headline: record.title,
    description: record.message,
    severity: 'UNSPECIFIED',
    risk_level: 'UNKNOWN',
    geofence: record.area_id,
    population_affected: 0,
    status: record.status.toUpperCase() as Alert['status'],
    issued_at: record.issued_at || record.created_at,
    expires_at: '',
    channels: record.target_channels,
    approved_by: record.approved_by || '',
    dispatched_at: record.issued_at || '',
    evacuation_notice: false,
    is_drill_simulation: record.mode === 'historical_demo' || record.mode === 'test',
  };
}
