describe('config/modal', () => {
  const requiredEnv = {
    MODAL_WEBHOOK_URL: 'https://modal.example/webhook',
    MODAL_WEBHOOK_SECRET: 'shared-secret',
  };
  const originalEnv = { ...process.env };

  beforeEach(() => {
    jest.resetModules();
    process.env = { ...originalEnv };
  });

  afterAll(() => {
    process.env = originalEnv;
  });

  it('exports the webhook URL and secret when both env vars are set', () => {
    Object.assign(process.env, requiredEnv);

    expect(require('../../src/config/modal')).toEqual(requiredEnv);
  });

  it.each(Object.keys(requiredEnv))('throws at load time when %s is missing', (missingKey) => {
    Object.assign(process.env, requiredEnv);
    delete process.env[missingKey];

    expect(() => require('../../src/config/modal')).toThrow(missingKey);
  });
});
