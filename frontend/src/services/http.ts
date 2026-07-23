export async function requireOk(response: Response, fallbackMessage: string): Promise<Response> {
  if (response.ok) return response;

  let message = fallbackMessage;
  try {
    const body = await response.json();
    if (body && typeof body.detail === 'string' && body.detail.trim()) {
      message = body.detail;
    } else if (body && typeof body.message === 'string' && body.message.trim()) {
      message = body.message;
    }
  } catch {
    // Non-JSON failures still surface the operation-specific fallback.
  }

  throw new Error(message);
}
