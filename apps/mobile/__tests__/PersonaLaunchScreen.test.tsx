/**
 * PersonaLaunchScreen render tests.
 * Tests are written but NOT run in this phase.
 */

import React from "react";
import { render, fireEvent, waitFor } from "@testing-library/react-native";

jest.mock("../src/api/identity", () => ({
  startInquiry: jest.fn(),
  getVerificationState: jest.fn(),
}));
jest.mock("expo-secure-store", () => ({
  setItemAsync: jest.fn().mockResolvedValue(undefined),
  getItemAsync: jest.fn().mockResolvedValue(null),
  deleteItemAsync: jest.fn().mockResolvedValue(undefined),
}));

const mockNavigation = { navigate: jest.fn() } as any;

import { PersonaLaunchScreen } from "../src/screens/identity/PersonaLaunchScreen";
import * as identityApi from "../src/api/identity";

describe("PersonaLaunchScreen", () => {
  beforeEach(() => jest.clearAllMocks());

  it("renders Start verification button initially", () => {
    const { getByTestId } = render(<PersonaLaunchScreen navigation={mockNavigation} />);
    expect(getByTestId("persona-launch-button")).toBeTruthy();
  });

  it("shows soft block messaging", () => {
    const { getByText } = render(<PersonaLaunchScreen navigation={mockNavigation} />);
    expect(getByText(/Soft requirement/)).toBeTruthy();
    expect(getByText(/optional/)).toBeTruthy();
  });

  it("calls startInquiry on button press", async () => {
    (identityApi.startInquiry as jest.Mock).mockResolvedValue({
      persona_inquiry_id: "inq_test123",
      persona_session_token: "token_abc",
    });

    const { getByTestId } = render(<PersonaLaunchScreen navigation={mockNavigation} />);
    fireEvent.press(getByTestId("persona-launch-button"));

    await waitFor(() => {
      expect(identityApi.startInquiry).toHaveBeenCalled();
    });
  });

  it("shows error on startInquiry failure", async () => {
    (identityApi.startInquiry as jest.Mock).mockRejectedValue({
      error: { message: "Persona API not configured." },
    });

    const { getByTestId, findByText } = render(<PersonaLaunchScreen navigation={mockNavigation} />);
    fireEvent.press(getByTestId("persona-launch-button"));

    await findByText(/not configured/);
  });
});
