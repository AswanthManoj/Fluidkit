import { createHmac } from 'node:crypto';

export function signRequest(): string {
  const secret = process.env.FLUIDKIT_SECRET;
  if (!secret) throw new Error('FLUIDKIT_SECRET environment variable is not set');
  const ts = String(Math.floor(Date.now() / 1000));
  const sig = createHmac('sha256', secret).update(ts).digest('hex');
  return `${ts}.${sig}`;
}
