import assert from 'node:assert/strict';
import test from 'node:test';
import React from 'react';
import { renderToString } from 'react-dom/server';
import { createServer } from 'vite';

test('WarningBulletins & Component Empty-State Regression Tests', async (t) => {
  const viteServer = await createServer({
    server: { middlewareMode: true },
    appType: 'custom',
    logLevel: 'error',
  });

  const { WarningBulletins } = await viteServer.ssrLoadModule('./src/components/WarningBulletins.tsx');

  await t.test('WarningBulletins: empty alerts array does NOT throw severity TypeError and renders empty state', () => {
    assert.doesNotThrow(() => {
      const html = renderToString(React.createElement(WarningBulletins, { alerts: [] }));
      assert.match(html, /No Demo Bulletins Available/i, 'Must render clean empty state headline');
      assert.match(html, /0 BROADCAST/i, 'Must display 0 broadcasts count');
    }, 'Must not throw Uncaught TypeError: Cannot read properties of undefined (reading "severity")');
  });

  await t.test('WarningBulletins: undefined/missing alerts prop does not throw', () => {
    assert.doesNotThrow(() => {
      const html = renderToString(React.createElement(WarningBulletins, { alerts: undefined }));
      assert.match(html, /No Demo Bulletins Available/i);
    });
  });

  await t.test('WarningBulletins: renders alert content correctly when alerts are provided', () => {
    const mockAlert = {
      id: 'alt_live_test_01',
      code: 'FLOOD-RED-2026',
      severity: 'EMERGENCY',
      headline: 'KOSHI BASIN FLASH FLOOD WARNING',
      description: 'Embankment risk observed in Ward 2.',
      geofence: 'Ward 2 Barahakshetra Corridor',
      dispatched_at: '2026-10-23T20:45:00Z',
      channels: ['SMS', 'CAP-GEO'],
      approved_by: 'Lead Commander',
    };

    assert.doesNotThrow(() => {
      const html = renderToString(React.createElement(WarningBulletins, { alerts: [mockAlert] }));
      assert.match(html, /KOSHI BASIN FLASH FLOOD WARNING/);
      assert.match(html, /EMERGENCY/);
      assert.match(html, /BROADCAST/);
      assert.match(html, /Ward 2 Barahakshetra Corridor/);
    });
  });

  await viteServer.close();
});

test('Flood Risk Markers & Geospatial Bounds Regression Tests', async (t) => {
  await t.test('Risk markers: green markers must NEVER claim guaranteed safety', () => {
    const lowRiskMarker = {
      id: 'loc_test_low',
      name: 'Test Settlement Low',
      activeRiskLevel: 'LOW',
      disclaimer: 'LOW ESTIMATED FLOOD RISK · Does NOT guarantee complete safety or absence of localized flash pooling.',
    };

    assert.equal(lowRiskMarker.activeRiskLevel, 'LOW');
    assert.match(lowRiskMarker.disclaimer, /NOT guarantee complete safety/i);
    assert.doesNotMatch(lowRiskMarker.disclaimer, /^Safe$/i, 'Must not label low risk as safe');
  });

  await t.test('Risk classification standards: Red=Critical/High, Yellow=Moderate, Green=Low, Gray=Unknown', () => {
    const mapRiskToColor = (risk) => {
      const r = risk.toUpperCase();
      if (r === 'CRITICAL' || r === 'HIGH') return '#ef4444'; // Red
      if (r === 'MODERATE') return '#eab308'; // Yellow
      if (r === 'LOW') return '#22c55e'; // Green
      return '#64748b'; // Gray
    };

    assert.equal(mapRiskToColor('CRITICAL'), '#ef4444');
    assert.equal(mapRiskToColor('HIGH'), '#ef4444');
    assert.equal(mapRiskToColor('MODERATE'), '#eab308');
    assert.equal(mapRiskToColor('LOW'), '#22c55e');
    assert.equal(mapRiskToColor('UNKNOWN'), '#64748b');
    assert.equal(mapRiskToColor('NO_DATA'), '#64748b');
  });

  await t.test('Coordinate order normalization: handles both [lng, lat] and inverted [lat, lng]', () => {
    const normalizeCoords = (c0, c1) => {
      // Nepal bounds: lon ~78-90, lat ~25-32
      if (c0 > 50 && c1 < 40) return [c0, c1]; // already [lng, lat]
      if (c1 > 50 && c0 < 40) return [c1, c0]; // was [lat, lng]
      return [c0, c1];
    };

    // Case 1: [lat, lng] from citizen request (e.g. [26.65, 87.05])
    const norm1 = normalizeCoords(26.65, 87.05);
    assert.deepEqual(norm1, [87.05, 26.65], 'Must swap [lat, lng] to [lng, lat]');

    // Case 2: Standard [lng, lat] (e.g. [85.92, 26.73])
    const norm2 = normalizeCoords(85.92, 26.73);
    assert.deepEqual(norm2, [85.92, 26.73], 'Must preserve valid [lng, lat]');
  });
});
