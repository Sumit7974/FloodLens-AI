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
  return {
    id: record.id,
    requester_name: 'Citizen (identity restricted)',
    contact_number: 'Not provided by API',
    timestamp: record.created_at,
    category: categoryMap[record.category],
    urgency: 'MEDIUM', // Presentation only; not assessed or ranked by the backend.
    urgency_score: 'NOT TRIAGED · demo presentation placeholder',
    status: viewStatus,
    handoff_status: viewStatus,
    people_count: record.people_count,
    location_name: 'Location available to authorized officers',
    coordinates: [record.latitude, record.longitude],
    landmark: record.details || 'No description provided',
    notes: [
      'Authenticated database record. Urgency has not been assessed by backend.',
      record.status_notes || '',
    ].filter(Boolean).join(' '),
    authority_handoff_target: record.assigned_to || undefined,
    authority_verification: 'Historical/test review; not an operational response confirmation',
    activity_log: [
      { timestamp: record.created_at, action: 'Assistance report recorded in backend', author: 'FloodLens historical/test backend' },
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
