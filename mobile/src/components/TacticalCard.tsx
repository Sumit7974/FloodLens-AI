import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity, StyleProp, ViewStyle } from 'react-native';
import { THEME } from '../constants/theme';
import { BadgeVariant } from '../types';
import { StatusPill } from './StatusPill';

export interface TacticalCardProps {
  title: string;
  icon?: React.ComponentType<{ size?: number; color?: string }> | React.ReactNode;
  badgeText?: string;
  badgeVariant?: BadgeVariant;
  value?: string | number;
  subtext?: string;
  children?: React.ReactNode;
  onPress?: () => void;
  style?: StyleProp<ViewStyle>;
  indicatorColor?: string;
}

export const TacticalCard: React.FC<TacticalCardProps> = ({
  title,
  icon,
  badgeText,
  badgeVariant = 'info',
  value,
  subtext,
  children,
  onPress,
  style,
  indicatorColor,
}) => {
  const CardContainer = onPress ? TouchableOpacity : View;

  const renderIcon = () => {
    if (!icon) return null;
    if (React.isValidElement(icon)) {
      return icon;
    }
    const IconComponent = icon as React.ComponentType<{ size?: number; color?: string }>;
    return <IconComponent size={16} color={indicatorColor || THEME.colors.cyan} />;
  };

  return (
    <CardContainer
      onPress={onPress}
      activeOpacity={onPress ? 0.75 : 1}
      style={[styles.card, style]}
    >
      {/* Top Header: Title, Icon, Badge */}
      <View style={styles.headerRow}>
        <View style={styles.titleGroup}>
          {renderIcon() && <View style={styles.iconWrapper}>{renderIcon()}</View>}
          <Text style={styles.titleText}>{title}</Text>
        </View>

        {badgeText && (
          <StatusPill
            label={badgeText}
            variant={badgeVariant}
            showDot={true}
          />
        )}
      </View>

      {/* Main Metric Value */}
      {value !== undefined && (
        <View style={styles.valueRow}>
          <Text style={styles.valueText}>{value}</Text>
        </View>
      )}

      {/* Secondary / Subtext Details */}
      {subtext && (
        <Text style={styles.subtext}>{subtext}</Text>
      )}

      {/* Embedded Children */}
      {children && <View style={styles.childrenContainer}>{children}</View>}
    </CardContainer>
  );
};

const styles = StyleSheet.create({
  card: {
    backgroundColor: THEME.colors.cardBg,
    borderRadius: THEME.borderRadius.lg,
    borderWidth: 1,
    borderColor: THEME.colors.cardBorder,
    padding: THEME.spacing.lg,
    marginBottom: THEME.spacing.md,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 3,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: THEME.spacing.xs,
  },
  titleGroup: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
    marginRight: THEME.spacing.sm,
  },
  iconWrapper: {
    marginRight: THEME.spacing.sm,
    padding: 4,
    borderRadius: THEME.borderRadius.sm,
    backgroundColor: 'rgba(255, 255, 255, 0.05)',
  },
  titleText: {
    fontSize: THEME.typography.cardTitleSize,
    fontWeight: '800',
    color: THEME.colors.textSecondary,
    letterSpacing: 1,
    textTransform: 'uppercase',
  },
  valueRow: {
    marginVertical: THEME.spacing.xs,
  },
  valueText: {
    fontSize: THEME.typography.metricDisplaySize,
    fontWeight: '900',
    color: THEME.colors.textPrimary,
    letterSpacing: 0.5,
  },
  subtext: {
    fontSize: THEME.typography.captionSize,
    color: THEME.colors.textMuted,
    marginTop: 2,
    lineHeight: 16,
  },
  childrenContainer: {
    marginTop: THEME.spacing.md,
    paddingTop: THEME.spacing.sm,
    borderTopWidth: 1,
    borderTopColor: 'rgba(30, 41, 59, 0.5)',
  },
});

export default TacticalCard;
