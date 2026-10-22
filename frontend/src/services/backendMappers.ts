import type { HelpRequest, AuthorityHandoffStatus, RequestCategory } from '../types';
import type { AssistanceRecord } from './backendApi';

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
