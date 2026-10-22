import React from 'react';
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  type TextInputProps,
  View,
  type ViewProps,
} from 'react-native';

export const C = {
  bg: '#060e1c', surface: '#0d1d30', border: '#223a52',
  text: '#f5f7fc', muted: '#9db3c7', aqua: '#5de0e6',
  green: '#60e4b2', yellow: '#ffce7c', red: '#ffa4a4',
  blue: '#2688ad',
};
export function Label({ children, muted = false, style }: {
  children: React.ReactNode; muted?: boolean; style?: object;
}) {
  return <Text style={[styles.text, muted && styles.muted, style]}>{children}</Text>;
}
export function Heading({ children }: { children: React.ReactNode }) {
  return <Text style={styles.heading}>{children}</Text>;
}
export function Panel({ children, style }: ViewProps) {
  return <View style={[styles.panel, style]}>{children}</View>;
}
export function Action({ title, onPress, busy = false, secondary = false, disabled = false }: {
  title: string; onPress: () => void; busy?: boolean; secondary?: boolean; disabled?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={title}
      disabled={disabled || busy}
      onPress={onPress}
      style={({ pressed }) => [
        styles.action, secondary && styles.actionSecondary,
        (pressed || disabled || busy) && { opacity: 0.58 },
      ]}
    >
      {busy ? <ActivityIndicator color={C.bg} /> : <Text style={[styles.actionText, secondary && { color: C.aqua }]}>{title}</Text>}
    </Pressable>
  );
}
export function Field({ label, ...props }: TextInputProps & { label: string }) {
  return (
    <View style={{ gap: 7 }}>
      <Label muted>{label}</Label>
      <TextInput
        accessibilityLabel={label}
        placeholderTextColor={C.muted}
        autoCapitalize="none"
        style={styles.input}
        {...props}
      />
    </View>
  );
}
export function Banner({ children, warning = false }: {
  children: React.ReactNode; warning?: boolean;
}) {
  return (
    <View style={[styles.banner, warning && { borderColor: '#765631', backgroundColor: '#241b13' }]}>
      <Text style={{ color: warning ? C.yellow : C.aqua, fontSize: 12, lineHeight: 19 }}>{children}</Text>
    </View>
  );
}
export function Pill({ children, color = C.aqua }: { children: React.ReactNode; color?: string }) {
  return <View style={styles.pill}><Text style={{ color, fontSize: 11, fontWeight: '700' }}>{children}</Text></View>;
}
export function Placeholder({ children }: { children: React.ReactNode }) {
  return <Panel><Label muted>{children}</Label></Panel>;
}
export function formatUtc(value: string | null | undefined): string {
  if (!value) return 'Not reported';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString();
}
export function evidenceAge(value: string | null | undefined): string {
  if (!value) return 'Freshness unknown';
  const ms = Date.now() - new Date(value).getTime();
  if (!Number.isFinite(ms) || ms < 0) return 'Timestamp unverified';
  const minutes = Math.floor(ms / 60000);
  if (minutes > 24 * 60) return `Old data: ${Math.floor(minutes / (24 * 60))}d ago`;
  if (minutes > 60) return `${Math.floor(minutes / 60)}h ago`;
  return `${minutes} min ago`;
}
const styles = StyleSheet.create({
  text: { color: C.text, fontSize: 14, lineHeight: 21 },
  muted: { color: C.muted },
  heading: { color: C.text, fontSize: 22, fontWeight: '800', letterSpacing: 0.2, marginBottom: 3 },
  panel: { padding: 15, backgroundColor: C.surface, borderColor: C.border, borderWidth: 1, borderRadius: 14, gap: 9 },
  action: { backgroundColor: C.aqua, borderRadius: 12, paddingVertical: 13, paddingHorizontal: 15, minHeight: 44, justifyContent: 'center', alignItems: 'center' },
  actionSecondary: { backgroundColor: 'transparent', borderColor: C.aqua, borderWidth: 1 },
  actionText: { fontSize: 14, color: C.bg, fontWeight: '800' },
  input: { borderColor: C.border, borderWidth: 1, borderRadius: 10, padding: 11, color: C.text, backgroundColor: '#081524', fontSize: 15, minHeight: 44 },
  banner: { borderWidth: 1, borderColor: C.blue, borderRadius: 12, padding: 12, backgroundColor: '#102334' },
  pill: { alignSelf: 'flex-start', paddingVertical: 5, paddingHorizontal: 9, backgroundColor: '#183147', borderRadius: 100 },
});
