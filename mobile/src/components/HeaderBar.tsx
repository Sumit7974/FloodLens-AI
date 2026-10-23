import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { THEME, DEFAULT_COORDINATES } from '../constants/theme';
import { StatusPill } from './StatusPill';

export interface HeaderBarProps {
  backendConnected: boolean;
  latencyMs?: number;
  sectorName?: string;
}

export const HeaderBar: React.FC<HeaderBarProps> = ({
  backendConnected,
  latencyMs,
  sectorName = DEFAULT_COORDINATES.koshiBasin.sectorName,
}) => {
  return (
    <View style={styles.container}>
      {/* Top Banner: Brand & Heartbeat Status */}
      <View style={styles.topRow}>
        <View style={styles.titleContainer}>
          <Text style={styles.brandTitle}>
            FLOOD<Text style={styles.brandHighlight}>LENS</Text>
          </Text>
          <Text style={styles.brandSubtext}>// MOBILE COMMAND</Text>
        </View>

        <StatusPill
          label={backendConnected ? `LIVE ${latencyMs ? `${latencyMs}ms` : ''}` : 'OFFLINE'}
          variant={backendConnected ? 'success' : 'destructive'}
          showDot={true}
        />
      </View>

      {/* Operational Sector Banner */}
      <View style={styles.sectorRow}>
        <View style={styles.sectorBadge}>
          <Text style={styles.sectorLabel}>SECTOR</Text>
          <Text style={styles.sectorValue}>{sectorName}</Text>
        </View>
        <Text style={styles.uplinkText}>ORBITAL UPLINK 10HZ</Text>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    backgroundColor: THEME.colors.cardBg,
    borderBottomWidth: 1,
    borderBottomColor: THEME.colors.cardBorder,
    paddingHorizontal: THEME.spacing.lg,
    paddingTop: THEME.spacing.md,
    paddingBottom: THEME.spacing.md,
  },
  topRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: THEME.spacing.xs,
  },
  titleContainer: {
    flexDirection: 'row',
    alignItems: 'baseline',
  },
  brandTitle: {
    fontSize: THEME.typography.headerSize,
    fontWeight: '900',
    color: THEME.colors.textPrimary,
    letterSpacing: 1.5,
  },
  brandHighlight: {
    color: THEME.colors.cyan,
  },
  brandSubtext: {
    fontSize: THEME.typography.captionSize,
    fontWeight: '700',
    color: THEME.colors.textSecondary,
    marginLeft: 6,
    letterSpacing: 1,
  },
  sectorRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: 4,
    paddingTop: 6,
    borderTopWidth: 1,
    borderTopColor: 'rgba(30, 41, 59, 0.5)',
  },
  sectorBadge: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  sectorLabel: {
    fontSize: THEME.typography.microSize,
    fontWeight: '800',
    color: THEME.colors.cyan,
    backgroundColor: 'rgba(6, 182, 212, 0.1)',
    paddingHorizontal: 4,
    paddingVertical: 1,
    borderRadius: 3,
    marginRight: 6,
    letterSpacing: 0.5,
  },
  sectorValue: {
    fontSize: THEME.typography.captionSize,
    fontWeight: '700',
    color: THEME.colors.textPrimary,
    letterSpacing: 0.6,
  },
  uplinkText: {
    fontSize: THEME.typography.microSize,
    color: THEME.colors.textMuted,
    fontFamily: 'monospace',
    letterSpacing: 0.8,
  },
});

export default HeaderBar;
