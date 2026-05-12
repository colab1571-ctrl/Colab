/**
 * SignUpScreen render tests.
 *
 * Uses React Native Testing Library.
 * Tests do NOT run network calls — all API calls are mocked.
 * Tests are written but NOT run in this phase (per spec constraint).
 */

import React from "react";
import { render, fireEvent, waitFor } from "@testing-library/react-native";

// Mock the auth API module
jest.mock("../src/api/auth", () => ({
  signupEmail: jest.fn(),
  signupPhoneStart: jest.fn(),
}));

// Mock expo-secure-store
jest.mock("expo-secure-store", () => ({
  setItemAsync: jest.fn().mockResolvedValue(undefined),
  getItemAsync: jest.fn().mockResolvedValue(null),
  deleteItemAsync: jest.fn().mockResolvedValue(undefined),
}));

// Mock navigation
const mockNavigate = jest.fn();
const mockNavigation = { navigate: mockNavigate } as any;

import { SignUpScreen } from "../src/screens/auth/SignUpScreen";
import * as authApi from "../src/api/auth";

describe("SignUpScreen", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("renders email and phone tabs", () => {
    const { getByText } = render(<SignUpScreen navigation={mockNavigation} />);
    expect(getByText("Email")).toBeTruthy();
    expect(getByText("Phone")).toBeTruthy();
  });

  it("renders age attestation checkbox", () => {
    const { getByTestId } = render(<SignUpScreen navigation={mockNavigation} />);
    expect(getByTestId("age-checkbox")).toBeTruthy();
  });

  it("renders ToS acceptance checkbox", () => {
    const { getByTestId } = render(<SignUpScreen navigation={mockNavigation} />);
    expect(getByTestId("tos-checkbox")).toBeTruthy();
  });

  it("shows error when age not attested on submit", async () => {
    const { getByTestId, getByText } = render(<SignUpScreen navigation={mockNavigation} />);
    const emailInput = getByTestId("signup-email-input");
    const passwordInput = getByTestId("signup-password-input");

    fireEvent.changeText(emailInput, "test@example.com");
    fireEvent.changeText(passwordInput, "Str0ng!Password");
    fireEvent.press(getByTestId("signup-submit"));

    await waitFor(() => {
      expect(getByText("You must be 18 or older to use Colab.")).toBeTruthy();
    });
  });

  it("shows error when ToS not accepted", async () => {
    const { getByTestId, getByText } = render(<SignUpScreen navigation={mockNavigation} />);

    // Check age box but not ToS
    fireEvent.press(getByTestId("age-checkbox"));
    fireEvent.changeText(getByTestId("signup-email-input"), "test@example.com");
    fireEvent.changeText(getByTestId("signup-password-input"), "Str0ng!Password");
    fireEvent.press(getByTestId("signup-submit"));

    await waitFor(() => {
      expect(getByText(/accept the Terms/)).toBeTruthy();
    });
  });

  it("calls signupEmail with correct params on submit", async () => {
    const mockTokens = {
      user_id: "user-123",
      access_token: "access.token",
      refresh_token: "refresh.token",
      token_type: "Bearer" as const,
      expires_in: 900,
    };
    (authApi.signupEmail as jest.Mock).mockResolvedValue(mockTokens);

    const { getByTestId } = render(<SignUpScreen navigation={mockNavigation} />);

    fireEvent.press(getByTestId("age-checkbox"));
    fireEvent.press(getByTestId("tos-checkbox"));
    fireEvent.changeText(getByTestId("signup-email-input"), "test@example.com");
    fireEvent.changeText(getByTestId("signup-password-input"), "Str0ng!Password99");
    fireEvent.press(getByTestId("signup-submit"));

    await waitFor(() => {
      expect(authApi.signupEmail).toHaveBeenCalledWith({
        email: "test@example.com",
        password: "Str0ng!Password99",
      });
    });
  });

  it("navigates to Verify screen after successful email signup", async () => {
    const mockTokens = {
      user_id: "user-123",
      access_token: "access.token",
      refresh_token: "refresh.token",
      token_type: "Bearer" as const,
      expires_in: 900,
    };
    (authApi.signupEmail as jest.Mock).mockResolvedValue(mockTokens);

    const { getByTestId } = render(<SignUpScreen navigation={mockNavigation} />);

    fireEvent.press(getByTestId("age-checkbox"));
    fireEvent.press(getByTestId("tos-checkbox"));
    fireEvent.changeText(getByTestId("signup-email-input"), "test@example.com");
    fireEvent.changeText(getByTestId("signup-password-input"), "Str0ng!Password99");
    fireEvent.press(getByTestId("signup-submit"));

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith("Verify", { email: "test@example.com" });
    });
  });

  it("shows API error message on signup failure", async () => {
    (authApi.signupEmail as jest.Mock).mockRejectedValue({
      error: { message: "An account with this email already exists." },
    });

    const { getByTestId, findByTestId } = render(<SignUpScreen navigation={mockNavigation} />);

    fireEvent.press(getByTestId("age-checkbox"));
    fireEvent.press(getByTestId("tos-checkbox"));
    fireEvent.changeText(getByTestId("signup-email-input"), "test@example.com");
    fireEvent.changeText(getByTestId("signup-password-input"), "Str0ng!Password99");
    fireEvent.press(getByTestId("signup-submit"));

    const errorEl = await findByTestId("signup-error");
    expect(errorEl.props.children).toContain("already exists");
  });

  it("renders Apple and Google sign-in buttons", () => {
    const { getByTestId } = render(<SignUpScreen navigation={mockNavigation} />);
    expect(getByTestId("apple-signup")).toBeTruthy();
    expect(getByTestId("google-signup")).toBeTruthy();
  });
});
