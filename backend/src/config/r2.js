require('dotenv').config();
const { S3Client } = require('@aws-sdk/client-s3');

const REQUIRED_ENV_VARS = ['R2_ENDPOINT', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY', 'R2_BUCKET_NAME'];
const missingEnvVars = REQUIRED_ENV_VARS.filter((key) => !process.env[key]);
if (missingEnvVars.length > 0) {
  throw new Error(`Missing required R2 environment variable(s): ${missingEnvVars.join(', ')}`);
}

const r2Client = new S3Client({
  region: 'auto',
  endpoint: process.env.R2_ENDPOINT, // e.g., 'https://<ACCOUNT_ID>.r2.cloudflarestorage.com'
  credentials: {
    accessKeyId: process.env.R2_ACCESS_KEY_ID,
    secretAccessKey: process.env.R2_SECRET_ACCESS_KEY,
  },
});

module.exports = r2Client;
