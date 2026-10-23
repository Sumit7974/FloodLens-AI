import React from 'react';
import { View, Text, StyleSheet, StyleProp, ViewStyle, TextStyle } from 'react-native';
import { THEME } from '../constants/theme';
import { BadgeVariant } from '../types';

export interface StatusPillProps {
  label: string;
  variant?: BadgeVariant;
  showDot?: boolean;
  style?: StyleProp<ViewStyle>;
  textStyle?: StyleProp<TextStyle>;
}

export const StatusPill: React.FC<StatusPillProps> = ({
  label,
  variant = 'info',
  showDot = true,
  style,
  textStyle,
}) => {
  const variantStyles = THEME.colors.status[variant] || THEME.colors.status.info;

  return (
    <View
      style={[
        styles.container,
        {
          backgroundColor: variantStyles.bg,
          borderColor: variantStyles.border,
        },
        style,
      ]}
    >
      {showDot && (
        <View
          style={[
            styles.dot,
            {
              backgroundColor: variantStyles.dot,
            },
          ]}
        />
      )}
      <Text
        style={[
          styles.label,
          {
            color: variantStyles.text,
          },
          textStyle,
        ]}
      >
        {label}
      </Text>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: THEME.borderRadius.full,
    borderWidth: 1,
    alignSelf: 'flex-start',
  },
  dot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    marginRight: 5,
  },
  label: {
    fontSize: THEME.typography.captionSize,
    fontWeight: '700',
    letterSpacing: 0.8,
    textTransform: 'uppercase',
  },
});

export default StatusPill;
