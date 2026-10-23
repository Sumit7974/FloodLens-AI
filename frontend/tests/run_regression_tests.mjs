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
