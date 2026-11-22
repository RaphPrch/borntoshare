/**
 * The reason of a failed event, readable. Some services record the raw error of a call, for instance
 * `503: {'error_code': 'SERVER_UNREACHABLE', 'message': 'The server dfs01 does not answer…'}`: only the message is
 * kept. Any other text is returned as it came.
 */
export function readableReason(raw: string | null | undefined): string {
  const text = String(raw ?? '').trim();
  if (!text) return '';
  // 'message': '…' (Python) or "message": "…" (JSON), the quote of the value may be either
  const match = text.match(/["']message["']\s*:\s*(["'])((?:\\.|(?!\1).)*)\1/s);
  if (match) return match[2].replace(/\\(["'])/g, '$1').trim();
  // An HTTP status in front of a plain text: « 503: Service Unavailable » → « Service Unavailable »
  return text.replace(/^\d{3}:\s+(?=[^{[])/, '');
}
