const localtunnel = require('localtunnel');

(async () => {
  const randomSuffix = Math.floor(1000 + Math.random() * 9000);
  const preferredSubdomain = `floodlens-ai-${randomSuffix}`;

  try {
    const tunnel = await localtunnel({
      port: 8000,
      subdomain: preferredSubdomain,
      host: 'https://localtunnel.me'
    });

    console.log('TUNNEL_ONLINE_SUCCESS');
    console.log(`PUBLIC_TUNNEL_URL=${tunnel.url}`);

    tunnel.on('close', () => {
      console.log('Tunnel connection closed');
    });

    tunnel.on('error', (err) => {
      console.error('Tunnel encountered an error:', err);
    });

    // Keep process alive indefinitely
    setInterval(() => {}, 1000 * 60 * 60);
  } catch (err) {
    console.error('Failed to create localtunnel:', err);
    process.exit(1);
  }
})();
