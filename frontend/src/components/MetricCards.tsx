import React from 'react';
import { TelemetryCommandCards } from './TelemetryCommandCards';
import type { MetricSummary } from '../types';

interface MetricCardsProps {
  metrics: MetricSummary;
}

export const MetricCards: React.FC<MetricCardsProps> = ({ metrics }) => {
  return <TelemetryCommandCards metrics={metrics} />;
};

export default MetricCards;
