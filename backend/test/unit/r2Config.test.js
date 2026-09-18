jest.mock('@aws-sdk/client-s3', () => ({ S3Client: jest.fn() }));

describe('config/r2', () => {
  const requiredEnv = {
    R2_ENDPOINT: 'https://r2.example.com',
    R2_ACCESS_KEY_ID: 'key',
    R2_SECRET_ACCESS_KEY: 'secret',
    R2_BUCKET_NAME: 'bucket',
  };
  const originalEnv = { ...process.env };

  beforeEach(() => {
    jest.resetModules();
    process.env = { ...originalEnv };
  });

  afterAll(() => {
    process.env = originalEnv;
  });

  it('constructs the client when all required env vars are set', () => {
    Object.assign(process.env, requiredEnv);
    expect(() => require('../../src/config/r2')).not.toThrow();
  });

  it.each(Object.keys(requiredEnv))('throws at load time when %s is missing', (missingKey) => {
    Object.assign(process.env, requiredEnv);
    delete process.env[missingKey];

    expect(() => require('../../src/config/r2')).toThrow(missingKey);
  });
});
