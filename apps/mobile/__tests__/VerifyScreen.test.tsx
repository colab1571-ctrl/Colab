/**
 * VerifyScreen render tests — email OTP verification.
 * Tests are written but NOT run in this phase.
 */

import React from "react";
import { render, fireEvent, waitFor } from "@testing-library/react-native";

jest.mock("../src/api/auth", () => ({
  emailVerifyFinish: jest.fn(),
  emailVerifyStart: jest.fn(),
}));
jest.mock("expo-secure-store", () => ({
  setItemAsync: jest.fn().mockResolvedValue(undefined),
  getItemAsync: jest.fn().mockResolvedValue(null),
  deleteItemAsync: jest.fn().mockResolvedValue(undefined),
}));

const mockNavigate = jest.fn();
const mockNavigation = { navigate: mockNavigate } as any;
const mockRoute = { params: { email: "verify@example.com" } } as any;

import { VerifyScreen } from "../src/screens/auth/VerifyScreen";
import * as authApi from "../src/api/auth";

describe("VerifyScreen", () => {
  beforeEach(() => jest.clearAllMocks());

  it("renders with email displayed", () => {
    const { getByText } = render(
      <VerifyScreen route={mockRoute} navigation={mockNavigation} />
    );
    expect(getByText(/verify@example.com/)).toBeTruthy();
  });

  it("renders OTP input", () => {
    const { getByTestId } = render(
      <VerifyScreen route={mockRoute} navigation={mockNavigation} />
    );
    expect(getByTestId("otp-input")).toBeTruthy();
  });

  it("shows error for short OTP", async () => {
    const { getByTestId, findByTestId } = render(
      <VerifyScreen route={mockRoute} navigation={mockNavigation} />
    );
    fireEvent.changeText(getByTestId("otp-input"), "123");
    fireEvent.press(getByTestId("verify-submit"));

    const err = await findByTestId("verify-error");
    expect(err.props.children).toContain("6-digit");
  });

  it("calls emailVerifyFinish with code on submit", async () => {
    (authApi.emailVerifyFinish as jest.Mock).mockResolvedValue({ email_verified: true });
    const { getByTestId } = render(
      <VerifyScreen route={mockRoute} navigation={mockNavigation} />
    );
    fireEvent.changeText(getByTestId("otp-input"), "123456");
    fireEvent.press(getByTestId("verify-submit"));

    await waitFor(() => {
      expect(authApi.emailVerifyFinish).toHaveBeenCalledWith({ code: "123456" });
    });
  });

  it("shows invalid code error on API failure", async () => {
    (authApi.emailVerifyFinish as jest.Mock).mockRejectedValue({
      error: { message: "Invalid or already used verification token." },
    });
    const { getByTestId, findByTestId } = render(
      <VerifyScreen route={mockRoute} navigation={mockNavigation} />
    );
    fireEvent.changeText(getByTestId("otp-input"), "000000");
    fireEvent.press(getByTestId("verify-submit"));

    const err = await findByTestId("verify-error");
    expect(err.props.children).toContain("Invalid");
  });
});
