import { installRuntimeErrorHandlers } from './logging';

export function bootstrapFrontendCore(): void {
  installRuntimeErrorHandlers();
}

