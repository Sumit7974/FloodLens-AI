import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

interface BeaconStatusCardProps {
  connected: boolean;
  latencyMs?: number;
  backendUrl: string;
}

export const BeaconStatusCard: React.FC<BeaconStatusCardProps> = ({
  connected,
  latencyMs,
  backendUrl,
}) => {
  return (
    <View style={[styles.card, connected ? styles.connectedBorder : styles.disconnectedBorder]}>
      <View style={styles.headerRow}>
        <Ionicons
          name={connected ? 'shield-checkmark' : 'cloud-offline'}
          size={20}
          color={connected ? '#10b981' : '#f43f5e'}
        />
        <Text style={styles.title}>
          {connected ? 'BACKEND LINK ACTIVE' : 'DISCONNECTED / STANDBY'}
        </Text>
      </View>
      <Text style={styles.urlText} numberOfLines={1}>
        {backendUrl}
      </Text>
      {connected && latencyMs !== undefined && (
        <Text style={styles.latencyText}>
          Telemetry Ping: {latencyMs}ms · PostGIS 3.6 Connected
        </Text>
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#0b1329',
    borderRadius: 8,
    borderWidth: 1,
    padding: 14,
    marginVertical: 10,
  },
  connectedBorder: {
    borderColor: '#06b6d4',
  },
  disconnectedBorder: {
    borderColor: '#f43f5e',
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 6,
  },
  title: {
    color: '#f8fafc',
    fontSize: 12,
    fontWeight: '700',
    letterSpacing: 0.5,
  },
  urlText: {
    color: '#94a3b8',
    fontSize: 11,
    fontFamily: 'monospace',
  },
  latencyText: {
    color: '#34d399',
    fontSize: 10,
    marginTop: 4,
    fontWeight: '600',
  },
});

export default BeaconStatusCard;
