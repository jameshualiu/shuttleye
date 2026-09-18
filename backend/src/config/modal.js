require('dotenv').config();

// Required at boot so a missing webhook secret/URL fails the deploy loudly
// instead of surfacing later as a silent Modal trigger failure per-request.
const REQUIRED_ENV_VARS = ['MODAL_WEBHOOK_URL', 'MODAL_WEBHOOK_SECRET'];
const missingEnvVars = REQUIRED_ENV_VARS.filter((key) => !process.env[key]);
if (missingEnvVars.length > 0) {
  throw new Error(`Missing required Modal webhook environment variable(s): ${missingEnvVars.join(', ')}`);
}

module.exports = {
  MODAL_WEBHOOK_URL: process.env.MODAL_WEBHOOK_URL,
  MODAL_WEBHOOK_SECRET: process.env.MODAL_WEBHOOK_SECRET,
};
