/**
 * Identity API client — typed wrappers around identity-svc endpoints.
 */

const BASE_URL = process.env.EXPO_PUBLIC_API_BASE_URL ?? "https://api.colab.com";

export interface InquiryStartResponse {
  persona_inquiry_id: string;
  persona_session_token: string;
}

export interface IdentityVerificationState {
  user_id: string;
  persona_inquiry_id: string | null;
  status: "pending" | "approved" | "declined" | "needs_review";
  face_age_signal: string | null;
  decision_at: string | null;
  created_at: string;
  updated_at: string;
}

async function request<T>(
  path: string,
  accessToken: string,
  options: RequestInit = {}
): Promise<T> {
  const resp = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
      ...(options.headers as Record<string, string>),
    },
  });
  const data = await resp.json();
  if (!resp.ok) throw data;
  return data as T;
}

export async function startInquiry(accessToken: string): Promise<InquiryStartResponse> {
  return request<InquiryStartResponse>("/identity/inquiry/start", accessToken, {
    method: "POST",
  });
}

export async function getVerificationState(
  accessToken: string
): Promise<IdentityVerificationState> {
  return request<IdentityVerificationState>("/identity/verification", accessToken, {
    method: "GET",
  });
}
