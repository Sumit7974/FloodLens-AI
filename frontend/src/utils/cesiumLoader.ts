/**
 * Dynamic loader for CesiumJS from official CDN.
 * Ensures initial dashboard bundle remains fast and lightweight,
 * verifies WebGL capability, and avoids massive bundler overhead on laptop environments.
 */

// Global type declarations for window.Cesium
declare global {
  interface Window {
    Cesium?: any;
    CESIUM_BASE_URL?: string;
  }
}

let cesiumLoadingPromise: Promise<any> | null = null;

export function isWebGLAvailable(): boolean {
  try {
    const canvas = document.createElement('canvas');
    return Boolean(
      window.WebGLRenderingContext &&
        (canvas.getContext('webgl') || canvas.getContext('experimental-webgl'))
    );
  } catch {
    return false;
  }
}

export function loadCesium(): Promise<any> {
  if (typeof window === 'undefined') {
    return Promise.reject(new Error('Cesium can only be loaded in a browser environment.'));
  }

  if (window.Cesium) {
    return Promise.resolve(window.Cesium);
  }

  if (!isWebGLAvailable()) {
    return Promise.reject(
      new Error('WebGL is not supported or hardware acceleration is disabled in your browser.')
    );
  }

  if (cesiumLoadingPromise) {
    return cesiumLoadingPromise;
  }

  cesiumLoadingPromise = new Promise((resolve, reject) => {
    // 1. Set base URL for Cesium assets (Workers, Assets, Widgets)
    const baseUrl = 'https://cesium.com/downloads/cesiumjs/releases/1.121/Build/Cesium/';
    window.CESIUM_BASE_URL = baseUrl;

    // 2. Load Cesium Widgets CSS if not already present
    const cssId = 'cesium-widgets-css';
    if (!document.getElementById(cssId)) {
      const link = document.createElement('link');
      link.id = cssId;
      link.rel = 'stylesheet';
      link.href = `${baseUrl}Widgets/widgets.css`;
      document.head.appendChild(link);
    }

    // 3. Load Cesium JS
    const scriptId = 'cesium-core-js';
    let script = document.getElementById(scriptId) as HTMLScriptElement | null;
    if (!script) {
      script = document.createElement('script');
      script.id = scriptId;
      script.src = `${baseUrl}Cesium.js`;
      script.async = true;

      script.onload = () => {
        if (window.Cesium) {
          resolve(window.Cesium);
        } else {
          reject(new Error('Cesium script loaded but window.Cesium is not defined.'));
        }
      };

      script.onerror = () => {
        cesiumLoadingPromise = null;
        reject(new Error('Failed to load CesiumJS from CDN. Please check network connection.'));
      };

      document.body.appendChild(script);
    } else {
      // Script tag exists, wait for Cesium to be available
      const interval = setInterval(() => {
        if (window.Cesium) {
          clearInterval(interval);
          resolve(window.Cesium);
        }
      }, 50);

      setTimeout(() => {
        clearInterval(interval);
        if (!window.Cesium) {
          reject(new Error('Cesium script load timed out.'));
        }
      }, 10000);
    }
  });

  return cesiumLoadingPromise;
}
